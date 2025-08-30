# app/routers/upload_assets.py
from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from starlette.templating import Jinja2Templates

import asyncio, io, csv, json, re
from typing import List, Dict, Any

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# ---------- single-upload lock (OK for 1 replica) ----------
_in_progress = False
_lock = asyncio.Lock()
async def guard_start():
    global _in_progress
    async with _lock:
        if _in_progress:
            raise HTTPException(status_code=409, detail="Un autre fichier est en cours de traitement.")
        _in_progress = True
async def guard_end():
    global _in_progress
    async with _lock:
        _in_progress = False

# ---------- strict schema ----------
SCHEMA_BASE = [
    "SerialNumber","CFCode","region","CfnName","CustomerNumber","ProcessorType",
    "NumberSocket","NumberCore","Model","CustomerName","CustomerAddress",
    "PostCode","Country","OrderNumber","PONumber","BmcMacAddress",
    "Memory","HBA","BOSS","PERC","NVME","GPU"
]
# require at least one of each; allow these index ranges
GROUP_BOUNDS = {"HDD": 12, "EMBMAC": 3, "NIC": 6}
GROUP_RE = re.compile(r"^(hdd|embmac|nic)\s*_?\s*(\d+)$", re.IGNORECASE)

# ---------- helpers ----------
EMPTY_MARKERS = {"", "NA", "N/A", "NULL"}

def _norm_header(col: str) -> str:
    # strip spaces + strip BOM if present
    return col.strip().lstrip("\ufeff")

def _to_none(v: Any):
    if v is None: return None
    s = str(v).strip()
    return None if s == "" or s.upper() in EMPTY_MARKERS else s

def _is_blank_row(row: List[Any]) -> bool:
    for v in row:
        if v is None:
            continue
        s = str(v).strip()
        if s.upper() not in EMPTY_MARKERS and s != "":
            return False
    return True

def _is_empty_asset(obj: Dict[str, Any]) -> bool:
    base_all_none = all(obj.get(k) is None for k in SCHEMA_BASE)
    groups_empty = all(not obj.get(g.lower()) for g in GROUP_BOUNDS.keys())
    return base_all_none and groups_empty

def read_csv(blob: bytes, encoding: str, delimiter: str):
    text = blob.decode(encoding, errors="replace")
    first_line = text.splitlines()[0] if text else ""

    # auto-detect delimiter if the first line clearly uses ; or \t
    chosen = delimiter
    if delimiter == ",":
        if first_line.count(";") > first_line.count(","):
            chosen = ";"
        elif first_line.count("\t") > max(first_line.count(","), first_line.count(";")):
            chosen = "\t"

    f = io.StringIO(text, newline="")
    reader = csv.reader(f, delimiter=chosen)
    rows = list(reader)
    if not rows:
        raise HTTPException(status_code=422, detail="CSV vide.")
    header = [_norm_header(c) for c in rows[0]]
    body = rows[1:]
    return header, body

def validate_headers_strict(header: List[str]) -> None:
    base_required = set(SCHEMA_BASE)
    base_seen = set()
    group_counts = {g: 0 for g in GROUP_BOUNDS.keys()}
    unknown, dups = [], []
    seen_once = set()

    for col in header:
        if col in base_required:
            if col in seen_once: dups.append(col)
            seen_once.add(col)
            base_seen.add(col)
            continue
        m = GROUP_RE.match(col.replace(" ", ""))
        if m:
            g = m.group(1).upper()
            idx = int(m.group(2))
            if g not in GROUP_BOUNDS:
                unknown.append(col); continue
            if not (1 <= idx <= GROUP_BOUNDS[g]):
                raise HTTPException(status_code=422, detail=f"Colonne {col} hors plage pour {g} (1..{GROUP_BOUNDS[g]}).")
            group_counts[g] += 1
        else:
            unknown.append(col)

    missing_base = sorted(list(base_required - base_seen))
    missing_groups = [g for g, c in group_counts.items() if c < 1]

    if dups:
        raise HTTPException(status_code=422, detail=f"En-têtes dupliqués: {', '.join(dups)}.")
    if missing_base:
        raise HTTPException(status_code=422, detail=f"Colonnes obligatoires manquantes: {', '.join(missing_base)}.")
    if missing_groups:
        raise HTTPException(status_code=422, detail=f"Il faut au moins une colonne pour chacun: {', '.join(missing_groups)}.")
    if unknown:
        raise HTTPException(status_code=422, detail=f"Colonnes non autorisées: {', '.join(unknown)}.")

def transform_row_to_grouped_maps(header: List[str], row: List[str]) -> Dict[str, Any]:
    """
    Output structure:
    {
      ...base fields...,
      "hdd":    {"hdd1": "...", "hdd2": "...", ...},
      "embmac": {"embmac1": "...", ...},
      "nic":    {"nic1": "...", ...}
    }
    """
    out: Dict[str, Any] = {}

    # build group dicts
    grouped: Dict[str, Dict[str, Any]] = { "hdd": {}, "embmac": {}, "nic": {} }

    for i, raw in enumerate(header):
        col = raw.replace(" ", "")
        val = _to_none(row[i] if i < len(row) else None)
        m = GROUP_RE.match(col)
        if m:
            g = m.group(1).lower()              # hdd / embmac / nic
            idx = int(m.group(2))
            key = f"{g}{idx}"                   # e.g. "hdd3"
            grouped[g][key] = val
        else:
            out[raw] = val  # keep original header casing for base fields

    out["hdd"] = grouped["hdd"]
    out["embmac"] = grouped["embmac"]
    out["nic"] = grouped["nic"]
    return out

# ===================== ROUTES =====================

@router.get(path="/assets/upload", response_class=HTMLResponse)
async def get_upload_page(request: Request):
    return templates.TemplateResponse("upload_assets.html", {"request": request})

@router.post(path="/assets/upload", response_class=HTMLResponse)
async def upload_csv(
    request: Request,
    file: UploadFile = File(...),
    delimiter: str = Form(","),        # defaults; your form sends hidden fields
    encoding: str = Form("utf-8"),
):
    if file.content_type not in ["text/csv", "application/vnd.ms-excel"]:
        msg = "✘ Le fichier doit être un CSV."
        return templates.TemplateResponse("upload_assets.html", {"request": request, "message": msg}, status_code=400)

    try:
        await guard_start()
    except HTTPException as he:
        return templates.TemplateResponse("upload_assets.html", {"request": request, "message": he.detail}, status_code=409)

    try:
        blob = await file.read()
        if len(blob) > 20 * 1024 * 1024:
            msg = "✘ Fichier trop volumineux (>20 Mo)."
            return templates.TemplateResponse("upload_assets.html", {"request": request, "message": msg}, status_code=413)

        header, rows = read_csv(blob, encoding, delimiter)
        validate_headers_strict(header)

        # drop blank rows, transform, drop fully-empty assets
        clean_rows = [r for r in rows if not _is_blank_row(r)]
        objs = (transform_row_to_grouped_maps(header, r) for r in clean_rows)
        payload = [o for o in objs if not _is_empty_asset(o)]

        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        return StreamingResponse(
            io.BytesIO(data),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="assets_transformed.json"'}
        )

    except HTTPException as he:
        return templates.TemplateResponse("upload_assets.html", {"request": request, "message": he.detail}, status_code=he.status_code)
    except Exception as e:
        return templates.TemplateResponse("upload_assets.html", {"request": request, "message": f"Erreur: {e}"}, status_code=500)
    finally:
        await guard_end()
