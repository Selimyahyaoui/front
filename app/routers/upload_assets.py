# app/routers/upload_assets.py
from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from starlette.templating import Jinja2Templates

import asyncio, io, csv, json, re
from typing import List, Dict, Any, Tuple

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")  # <-- même que ton ancien code

# ---------- verrou simple : un seul traitement à la fois (OK 1 replica) ----------
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

# ---------- SCHEMA STRICT ----------
SCHEMA_BASE = [
    "SerialNumber","CFCode","region","CfnName","CustomerNumber","ProcessorType",
    "NumberSocket","NumberCore","Model","CustomerName","CustomerAddress",
    "PostCode","Country","OrderNumber","PONumber","BmcMacAddress",
    "Memory","HBA","BOSS","PERC","NVME","GPU"
]
# au moins 1 colonne pour chacun de ces groupes ; plages autorisées :
GROUP_BOUNDS = {"HDD": 12, "EMBMAC": 3, "NIC": 6}
GROUP_RE = re.compile(r"^(hdd|embmac|nic)\s*_?\s*(\d+)$", re.IGNORECASE)

# ---------- utils ----------
def read_csv(blob: bytes, encoding: str, delimiter: str) -> Tuple[List[str], List[List[str]]]:
    if delimiter == "tab":
        delimiter = "\t"
    text = blob.decode(encoding, errors="replace")
    f = io.StringIO(text, newline="")
    rows = list(csv.reader(f, delimiter=delimiter))
    if not rows:
        raise HTTPException(status_code=422, detail="CSV vide.")
    header = [c.strip() for c in rows[0]]
    return header, rows[1:]

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
        raise HTTPException(status_code=422, detail=f"Il faut au moins une colonne pour chacun: {', '.join(missing_groups)} (ex: {', '.join(g+'1' for g in missing_groups)}).")
    if unknown:
        raise HTTPException(status_code=422, detail=f"Colonnes non autorisées: {', '.join(unknown)}.")

def to_none(v: Any):
    if v is None: return None
    s = str(v).strip()
    return None if s=="" or s.upper() in {"NA","N/A","NULL"} else s

def transform_row(header: List[str], row: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    # pré-size des tableaux jusqu’au plus grand index présent dans le header
    max_idx = {g.lower(): 0 for g in GROUP_BOUNDS.keys()}
    for col in header:
        m = GROUP_RE.match(col.replace(" ", ""))
        if m:
            g = m.group(1).lower()
            idx = int(m.group(2))
            max_idx[g] = max(max_idx[g], idx)
    arrays = {g: [None]*max_idx[g] for g in max_idx}

    for i, col in enumerate(header):
        val = to_none(row[i] if i < len(row) else None)
        m = GROUP_RE.match(col.replace(" ", ""))
        if m:
            g = m.group(1).lower()
            idx = int(m.group(2))
            arrays[g][idx-1] = val
        else:
            out[col] = val

    # trim trailing None
    for g, arr in arrays.items():
        while arr and arr[-1] is None:
            arr.pop()
        out[g] = arr
    return out

# ===================== ENDPOINTS (même signature/UX que l’ancien) =====================

@router.get(path="/assets/upload", response_class=HTMLResponse)
async def get_upload_page(request: Request):
    # mêmes clés que ton ancien template : "message"
    return templates.TemplateResponse(name="upload_assets.html", context={"request": request})

@router.post(path="/assets/upload", response_class=HTMLResponse)
async def upload_csv(
    request: Request,
    file: UploadFile = File(...),
    delimiter: str = Form(","),        # mêmes champs optionnels si tu veux les ajouter au form
    encoding: str = Form("utf-8"),
):
    # même contrôle de type que l’ancien (strict)
    if file.content_type != "text/csv":
        message = "✘ Le fichier doit être un fichier CSV."
        return templates.TemplateResponse(name="upload_assets.html", context={"request": request, "message": message}, status_code=400)

    # verrou “un seul à la fois”
    try:
        await guard_start()
    except HTTPException as he:
        return templates.TemplateResponse(name="upload_assets.html", context={"request": request, "message": he.detail}, status_code=409)

    try:
        blob = await file.read()
        if len(blob) > 20 * 1024 * 1024:
            message = "✘ Fichier trop volumineux (> 20 Mo)."
            return templates.TemplateResponse(name="upload_assets.html", context={"request": request, "message": message}, status_code=413)

        header, rows = read_csv(blob, encoding, delimiter)
        # contrôle de saisie strict : toutes les colonnes de base + ≥1 HDD/EMBMAC/NIC ; aucune inconnue
        validate_headers_strict(header)

        # transformation : regroupement hdd/embmac/nic
        payload = [transform_row(header, r) for r in rows]
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

        # on renvoie directement le JSON en téléchargement (UX identique à avant: page → download)
        return StreamingResponse(
            io.BytesIO(data),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="assets_transformed.json"'}
        )

    except HTTPException as he:
        # on ré-affiche la page avec le message d’erreur (comme ton ancien code)
        return templates.TemplateResponse(name="upload_assets.html", context={"request": request, "message": he.detail}, status_code=he.status_code)
    except Exception as e:
        return templates.TemplateResponse(name="upload_assets.html", context={"request": request, "message": f"Erreur: {e}"}, status_code=500)
    finally:
        await guard_end()
