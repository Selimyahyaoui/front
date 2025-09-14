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
    "dbname": os.getenv("DB_NAME", "dell"),
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

@router.get("/ips", response_class=HTMLResponse)
def list_ips(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    q: str | None = Query(None, description="Search IP/VLAN/Hostname/Status"),
):
    """
    List IPs with pagination and optional search.
    Search applies to: ip_address, vlan_id (as text), hostname, status.
    """
    offset = (page - 1) * per_page
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # ----- COUNT with optional filter
            if q:
                like = f"%{q.lower()}%"
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM T_RefDhcp
                    WHERE
                        LOWER(COALESCE(ip_address, '')) LIKE %s OR
                        LOWER(COALESCE(CAST(vlan_id AS TEXT), '')) LIKE %s OR
                        LOWER(COALESCE(hostname, '')) LIKE %s OR
                        LOWER(COALESCE(status, '')) LIKE %s
                    """,
                    (like, like, like, like),
                )
            else:
                cur.execute("SELECT COUNT(*) FROM T_RefDhcp")
            total = cur.fetchone()[0]

            # ----- PAGE with same filter
            if q:
                like = f"%{q.lower()}%"
                cur.execute(
                    """
                    SELECT id, ip_address, vlan_id, hostname, status, assigned_date
                    FROM T_RefDhcp
                    WHERE
                        LOWER(COALESCE(ip_address, '')) LIKE %s OR
                        LOWER(COALESCE(CAST(vlan_id AS TEXT), '')) LIKE %s OR
                        LOWER(COALESCE(hostname, '')) LIKE %s OR
                        LOWER(COALESCE(status, '')) LIKE %s
                    ORDER BY id ASC
                    LIMIT %s OFFSET %s
                    """,
                    (like, like, like, like, per_page, offset),
                )
            else:
                cur.execute(
                    """
                    SELECT id, ip_address, vlan_id, hostname, status, assigned_date
                    FROM T_RefDhcp
                    ORDER BY id ASC
                    LIMIT %s OFFSET %s
                    """,
                    (per_page, offset),
                )
            rows = cur.fetchall()

        return templates.TemplateResponse(
            "ips.html",
            {
                "request": request,
                "ips": rows,
                "page": page,
                "per_page": per_page,
                "total": total,
                "q": q or "",
            },
        )
    finally:
        conn.close()
