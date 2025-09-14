# app/routers/ips.py
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from app.db.database import get_connection  # <- keep your existing helper

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Columns we show (keep in sync with the template)
COLUMNS = [
    "t_ref_dhcp_id",
    "t_ref_dhcp_network",
    "t_ref_dhcp_id_vlan",
    "t_ref_dhcp_t_site",
    "t_ref_dhcp_infoblox",
    "t_ref_dhcp_availability",
    "t_ref_dhcp_date_add",
]

@router.get("/ips", response_class=HTMLResponse)
def list_ips(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    q: str = Query("", description="Search in id, network, vlan, site, infoblox"),
):
    offset = (page - 1) * per_page

    where_sql = ""
    params = {}
    if q:
        where_sql = """
        WHERE
            CAST(t_ref_dhcp_id AS TEXT) ILIKE %(q)s
            OR t_ref_dhcp_network ILIKE %(q)s
            OR CAST(t_ref_dhcp_id_vlan AS TEXT) ILIKE %(q)s
            OR CAST(t_ref_dhcp_t_site AS TEXT) ILIKE %(q)s
            OR COALESCE(t_ref_dhcp_infoblox,'') ILIKE %(q)s
        """
        params["q"] = f"%{q}%"

    col_sql = ", ".join(COLUMNS)

    # Query
    with get_connection() as conn:
        with conn.cursor() as cur:
            # total count with same WHERE
            cur.execute(f"SELECT COUNT(*) FROM t_ref_dhcp {where_sql}", params)
            total = cur.fetchone()[0]

            cur.execute(
                f"""
                SELECT {col_sql}
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
