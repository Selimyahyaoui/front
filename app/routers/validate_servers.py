from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
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

@router.get("/servers/validate", response_class=HTMLResponse)
def show_pending_validations(request: Request, page: int = Query(1, ge=1), per_page: int = Query(10, ge=1, le=100)):
    offset = (page - 1) * per_page
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM T_ServerSts WHERE migration_status = 'PendingValidation'")
    total = cur.fetchone()[0]

    cur.execute("""
        SELECT id, hostname, site_source, site_target, planned_date
        FROM T_ServerSts
        WHERE migration_status = 'PendingValidation'
        ORDER BY planned_date DESC
        LIMIT %s OFFSET %s
    """, (per_page, offset))
    rows = cur.fetchall()
    conn.close()

    return templates.TemplateResponse("validate_servers.html", {
        "request": request,
        "servers": rows,
        "page": page,
        "per_page": per_page,
        "total": total
    })

@router.post("/servers/validate/decision")
def handle_validation(server_id: int = Form(...), decision: str = Form(...)):
    conn = get_connection()
    cur = conn.cursor()
    status = "Validated" if decision == "accept" else "Rejected"
    cur.execute("UPDATE T_ServerSts SET migration_status = %s WHERE id = %s", (status, server_id))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/servers/validate", status_code=303)
