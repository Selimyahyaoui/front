from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
import psycopg2
import os

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

@router.get("/assets", response_class=HTMLResponse)
def list_assets(request: Request, page: int = Query(1, ge=1), per_page: int = Query(10, ge=1, le=100)):
    offset = (page - 1) * per_page
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM T_AssetReport")
    total = cur.fetchone()[0]

    cur.execute("""
        SELECT id, serial_number, hostname, model, assigned_user, location
        FROM T_AssetReport
        ORDER BY id DESC
        LIMIT %s OFFSET %s
    """, (per_page, offset))
    rows = cur.fetchall()
    conn.close()

    return templates.TemplateResponse("assets.html", {
        "request": request,
        "assets": rows,
        "page": page,
        "per_page": per_page,
        "total": total
    })
