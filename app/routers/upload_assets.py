from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.templating import Jinja2Templates
import psycopg2
import csv
import os
import io

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "password"),
    "dbname": os.getenv("DB_NAME", "dell")
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

@router.get("/assets/upload", response_class=HTMLResponse)
async def get_upload_page(request: Request):
    return templates.TemplateResponse("upload_assets.html", {"request": request})

@router.post("/assets/upload", response_class=HTMLResponse)
async def upload_csv(request: Request, file: UploadFile = File(...)):
    message = ""
    if file.content_type != 'text/csv':
        message = "❌ Le fichier doit être un fichier CSV."
        return templates.TemplateResponse("upload_assets.html", {"request": request, "message": message})

    content = await file.read()
    csv_reader = csv.reader(io.StringIO(content.decode("utf-8")))

    try:
        conn = get_connection()
        cur = conn.cursor()
        for row in csv_reader:
            if len(row) < 5:
                continue  # skip incomplete rows
            cur.execute("""
                INSERT INTO T_AssetReport (serial_number, hostname, model, assigned_user, location)
                VALUES (%s, %s, %s, %s, %s)
            """, (row[0], row[1], row[2], row[3], row[4]))
        conn.commit()
        conn.close()
        message = "✅ Fichier CSV importé avec succès !"
    except Exception as e:
        message = f"❌ Erreur : {str(e)}"

    return templates.TemplateResponse("upload_assets.html", {"request": request, "message": message})
