from fastapi import APIRouter, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from pathlib import Path
import uuid, shutil

from app.services.assets import transform_csv_to_json

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

UPLOAD_DIR = Path("app/static/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@router.get("/assets/upload", response_class=HTMLResponse)
async def get_upload(request: Request):
    return templates.TemplateResponse("upload_assets.html", {"request": request})

@router.post("/assets/upload", response_class=HTMLResponse)
async def post_upload(request: Request, file: UploadFile = File(...)):
    if file.content_type not in ["text/csv", "application/vnd.ms-excel"]:
        return templates.TemplateResponse("upload_assets.html", {
            "request": request,
            "message": "✘ Le fichier doit être un CSV."
        }, status_code=400)

    tmp_name = f"upload_{uuid.uuid4().hex}.csv"
    tmp_path = UPLOAD_DIR / tmp_name
    with tmp_path.open("wb") as buf:
        shutil.copyfileobj(file.file, buf)

    try:
        json_path = transform_csv_to_json(str(tmp_path))
        msg = f"✔ Fichier traité et stocké sous : {json_path}"
        return templates.TemplateResponse("upload_assets.html", {"request": request, "message": msg})
    except Exception as e:
        return templates.TemplateResponse("upload_assets.html", {"request": request, "message": f"Erreur: {e}"}, status_code=500)
