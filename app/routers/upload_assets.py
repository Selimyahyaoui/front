from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from pathlib import Path
import os, shutil, uuid

# CSV -> JSON converter (your existing service)
from app.routers.services.assets import transform_csv_to_json

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# ----- paths
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/uploads"))
# This is the PV JSON we use as the lock (same pattern as add_order)
ASSETS_JSON_PATH = Path(os.getenv("JSON_OUTPUT_PATH", "/app/uploads/assets_transformed.json"))

def _ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p

def _is_locked() -> bool:
    """Lock = JSON file present and non-empty."""
    return ASSETS_JSON_PATH.exists() and ASSETS_JSON_PATH.stat().st_size > 0

@router.get("/assets/upload", response_class=HTMLResponse)
async def get_upload(request: Request):
    locked = _is_locked()
    return templates.TemplateResponse(
        "upload_assets.html",
        {
            "request": request,
            "locked": locked,
            "message_ok": None,
            "message_error": None,
            "json_path": str(ASSETS_JSON_PATH),
        },
    )

@router.post("/assets/upload", response_class=HTMLResponse)
async def post_upload(
    request: Request,
    file: UploadFile = File(...),
):
    # If locked, do not accept new uploads
    if _is_locked():
        return templates.TemplateResponse(
            "upload_assets.html",
            {
                "request": request,
                "locked": True,
                "message_ok": None,
                "message_error": (
                    "Un fichier JSON d’assets existe déjà sur le stockage. "
                    "La page est verrouillée tant que l’API DELETE n’a pas supprimé ce fichier."
                ),
                "json_path": str(ASSETS_JSON_PATH),
            },
            status_code=423,  # Locked
        )

    if file.content_type not in ("text/csv", "application/vnd.ms-excel", "application/octet-stream"):
        return templates.TemplateResponse(
            "upload_assets.html",
            {
                "request": request,
                "locked": False,
                "message_ok": None,
                "message_error": "Le fichier doit être un CSV.",
                "json_path": str(ASSETS_JSON_PATH),
            },
            status_code=400,
        )

    _ensure_dir(UPLOAD_DIR)

    # Save CSV into a temp file
    tmp_name = f"upload_{uuid.uuid4().hex}.csv"
    tmp_csv = UPLOAD_DIR / tmp_name
    try:
        with tmp_csv.open("wb") as buf:
            shutil.copyfileobj(file.file, buf)

        # Let your service convert the CSV to JSON (it returns the produced JSON path)
        produced_json_path = Path(transform_csv_to_json(str(tmp_csv)))

        # Move the produced JSON into our PV lock path (atomically replace if exists)
        _ensure_dir(ASSETS_JSON_PATH.parent)
        shutil.move(str(produced_json_path), str(ASSETS_JSON_PATH))

        msg = f"Fichier traité. JSON écrit : {ASSETS_JSON_PATH}"
        return templates.TemplateResponse(
            "upload_assets.html",
            {
                "request": request,
                "locked": True,  # now locked
                "message_ok": msg,
                "message_error": None,
                "json_path": str(ASSETS_JSON_PATH),
            },
        )
    except Exception as e:
        return templates.TemplateResponse(
            "upload_assets.html",
            {
                "request": request,
                "locked": False,
                "message_ok": None,
                "message_error": f"Erreur : {e}",
                "json_path": str(ASSETS_JSON_PATH),
            },
            status_code=500,
        )
    finally:
        # Best effort cleanup
        with contextlib.suppress(Exception):
            tmp_csv.unlink(missing_ok=True)
