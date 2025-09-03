# app/routers/upload_assets.py
from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from pathlib import Path
import os, shutil, uuid

from app.routers.services.assets import transform_csv_to_json

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _writable_dir(*candidates) -> Path:
    """
    Return the first directory from 'candidates' that is writable.
    If none are writable, raise a clear error. Ensures the dir exists.
    """
    for p in candidates:
        if not p:
            continue
        try:
            d = Path(p)
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".writetest"
            with probe.open("wb") as fh:
                fh.write(b"ok")
            probe.unlink(missing_ok=True)
            return d
        except Exception:
            continue
    raise RuntimeError("No writable temp directory found (tried: %s)" % ", ".join(map(str, candidates)))


# Prefer env var, but **force** fallback to /tmp (safe on OpenShift)
UPLOAD_DIR = _writable_dir(os.getenv("UPLOAD_DIR"), "/tmp")


@router.get("/assets/upload", response_class=HTMLResponse)
async def get_upload(request: Request):
    return templates.TemplateResponse("upload_assets.html", {"request": request})


@router.post("/assets/upload", response_class=HTMLResponse)
async def post_upload(request: Request, file: UploadFile = File(...)):
    # Accept common CSV content types
    if file.content_type not in ("text/csv", "application/vnd.ms-excel"):
        return templates.TemplateResponse(
            "upload_assets.html",
            {"request": request, "message": "✘ Le fichier doit être un CSV."},
            status_code=400,
        )

    # Save the uploaded file into a writable temp dir
    tmp_name = f"upload_{uuid.uuid4().hex}.csv"
    tmp_path = UPLOAD_DIR / tmp_name

    try:
        with tmp_path.open("wb") as buf:
            shutil.copyfileobj(file.file, buf)

        # Transform CSV -> JSON (service writes final JSON to /tmp/assets_transformed.json by default)
        json_path = transform_csv_to_json(str(tmp_path))

        return templates.TemplateResponse(
            "upload_assets.html",
            {"request": request, "message": f"✔ Fichier traité et stocké sous : {json_path}"},
        )

    except Exception as e:
        return templates.TemplateResponse(
            "upload_assets.html",
            {"request": request, "message": f"Erreur: {e}"},
            status_code=500,
        )
