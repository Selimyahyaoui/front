# app/routers/ips.py
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from app.db.database import get_connection  # <-- same helper you use elsewhere

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Keep this list in the exact order you want to display
COLUMNS = [
    "t_ref_dhcp_id",
    "t_ref_dhcp_t_site",
    "t_ref_dhcp_id_lan",
    "t_ref_dhcp_network",
    "t_ref_dhcp_add_by",
    "t_ref_dhcp_change_by",
    "t_ref_dhcp_date_update",
    "t_ref_dhcp_date_add",
    "t_ref_dhcp_infoblox",
    "t_ref_dhcp_availability",
]

COLSQL = ", ".join(COLUMNS)

@router.get("/ips", response_class=HTMLResponse)
def list_ips(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    q: str = Query("", description="Recherche"),
):
    offset = (page - 1) * per_page

    # WHERE (same for COUNT and SELECT)
    where_sql = ""
    params = {}
    if q:
        where_sql = """
        WHERE
            CAST(t_ref_dhcp_id AS TEXT) ILIKE %(q)s
            OR CAST(t_ref_dhcp_t_site AS TEXT) ILIKE %(q)s
            OR CAST(t_ref_dhcp_id_lan AS TEXT) ILIKE %(q)s
            OR COALESCE(t_ref_dhcp_network,'') ILIKE %(q)s
            OR COALESCE(t_ref_dhcp_add_by,'') ILIKE %(q)s
            OR COALESCE(t_ref_dhcp_change_by,'') ILIKE %(q)s
            OR COALESCE(t_ref_dhcp_infoblox,'') ILIKE %(q)s
            OR COALESCE(t_ref_dhcp_availability,'') ILIKE %(q)s
        """
        params["q"] = f"%{q}%"

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM t_ref_dhcp {where_sql}", params)
        total = cur.fetchone()[0]

        cur.execute(
            f"""
            SELECT {COLSQL}
            FROM t_ref_dhcp
            {where_sql}
            ORDER BY t_ref_dhcp_id ASC
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            {**params, "limit": per_page, "offset": offset},
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
            "q": q,
        },
    )
