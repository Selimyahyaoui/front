import asyncio, io, csv, json, re
from typing import Dict, Any, List, Tuple
from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from starlette.templating import Jinja2Templates

router = APIRouter(prefix="/assets/upload", tags=["assets-upload"])
templates = Jinja2Templates(directory="templates")

# --------- Verrou simple (1 seul traitement à la fois - OK 1 replica) ----------
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

# --------- SCHEMA STRICT (adapte au besoin) ----------
SCHEMA_BASE = [
    "SerialNumber","CFCode","region","CfnName","CustomerNumber","ProcessorType",
    "NumberSocket","NumberCore","Model","CustomerName","CustomerAddress",
    "PostCode","Country","OrderNumber","PONumber","BmcMacAddress",
    "Memory","HBA","BOSS","PERC","NVME","GPU"
]
GROUP_BOUNDS = {  # min imposé = 1 ; max = plage autorisée
    "HDD":    12,
    "EMBMAC": 3,
    "NIC":    6,
}
GROUP_RE = re.compile(r"^(hdd|embmac|nic)\s*_?\s*(\d+)$", re.IGNORECASE)

# --------- Utils ----------
def _read_csv(blob: bytes, encoding: str, delimiter: str) -> Tuple[List[str], List[List[str]]]:
    if delimiter == "tab": delimiter = "\t"
    text = blob.decode(encoding, errors="replace")
    f = io.StringIO(text, newline="")
    rows = list(csv.reader(f, delimiter=delimiter))
    if not rows: raise HTTPException(status_code=422, detail="CSV vide.")
    header = [c.strip() for c in rows[0]]
    return header, rows[1:]

def _validate_headers_strict(header: List[str]) -> Dict[str,int]:
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
                raise HTTPException(status_code=422, detail=f"Colonne {col} hors plage autorisée pour {g} (1..{GROUP_BOUNDS[g]}).")
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
        raise HTTPException(
            status_code=422,
            detail=f"Il faut au moins une colonne pour chacun: {', '.join(missing_groups)} (ex: {', '.join(g+'1' for g in missing_groups)})."
        )
    if unknown:
        raise HTTPException(status_code=422, detail=f"Colonnes non autorisées: {', '.join(unknown)}.")
    return group_counts

def _to_none(v):
    if v is None: return None
    s = str(v).strip()
    return None if s=="" or s.upper() in {"NA","N/A","NULL"} else s

def _transform_row(header: List[str], row: List[str]) -> Dict[str, any]:
    out: Dict[str, any] = {}
    # Taille max présente dans le header pour chaque groupe
    max_idx = {g.lower(): 0 for g in GROUP_BOUNDS.keys()}
    for col in header:
        m = GROUP_RE.match(col.replace(" ", ""))
        if m:
            g = m.group(1).lower()
            idx = int(m.group(2))
            max_idx[g] = max(max_idx[g], idx)
    arrays = {g: [None]*max_idx[g] for g in max_idx}

    for i, col in enumerate(header):
        val = _to_none(row[i] if i < len(row) else None)
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

# --------- Pages ----------
@router.get("")
async def upload_form(request: Request):
    return templates.TemplateResponse("assets_upload.html", {"request": request, "error": None})

@router.post("")
async def handle_upload(
    request: Request,
    file: UploadFile = File(...),
    delimiter: str = Form(","),
    encoding: str = Form("utf-8"),
):
    await guard_start()
    try:
        # Vérifs basiques
        name = (file.filename or "").lower()
        if not name.endswith(".csv"):
            return templates.TemplateResponse("assets_upload.html", {"request": request, "error": "Le fichier doit être .csv"}, status_code=400)

        blob = await file.read()
        if len(blob) > 20*1024*1024:
            return templates.TemplateResponse("assets_upload.html", {"request": request, "error": "Fichier trop volumineux (>20 Mo)."}, status_code=413)

        header, rows = _read_csv(blob, encoding, delimiter)
        _validate_headers_strict(header)

        payload = [_transform_row(header, r) for r in rows]
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

        # Retourne un téléchargement direct du JSON
        return StreamingResponse(
            io.BytesIO(data),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="assets_transformed.json"'}
        )
    except HTTPException as he:
        # Rendre proprement l’erreur sur le formulaire
        return templates.TemplateResponse("assets_upload.html", {"request": request, "error": he.detail}, status_code=he.status_code)
    finally:
        await guard_end()
