from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from app.db.database import get_connection  # ← same helper you already use

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ---------- Page: list IPs with search + pagination ----------
@router.get("/ips", response_class=HTMLResponse)
def list_ips(
    request: Request,
    q: str = Query("", description="search (id, site, vlan, network, hostname)"),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
):
    """
    Lists rows from supchain.t_ref_dhcp with 'catalog' look:
    - Search on id/site/vlan/network/infoblox (hostname)
    - Pagination, 'per page' selector
    """
    offset = (page - 1) * per_page
    params = {}  # used for both count and data queries

    where = []
    if q:
        # search across a few columns
        where.append(
            """(
                CAST(t_ref_dhcp_id AS TEXT) ILIKE %(kw)s
                OR CAST(t_ref_dhcp_t_site AS TEXT) ILIKE %(kw)s
                OR CAST(t_ref_dhcp_id_vlan AS TEXT) ILIKE %(kw)s
                OR t_ref_dhcp_network ILIKE %(kw)s
                OR t_ref_dhcp_infoblox ILIKE %(kw)s
            )"""
        )
        params["kw"] = f"%{q.strip()}%"

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    # --- COUNT ---
    count_sql = f"SELECT COUNT(*) FROM supchain.t_ref_dhcp {where_sql};"

    # --- PAGE DATA ---
    data_sql = f"""
        SELECT
            t_ref_dhcp_id,
            t_ref_dhcp_t_site,
            t_ref_dhcp_id_vlan,
            t_ref_dhcp_network,
            t_ref_dhcp_add_by,
            t_ref_dhcp_change_by,
            t_ref_dhcp_date_update,
            t_ref_dhcp_date_add,
            t_ref_dhcp_infoblox,
            t_ref_dhcp_availability
        FROM supchain.t_ref_dhcp
        {where_sql}
        ORDER BY t_ref_dhcp_id ASC
        LIMIT %(limit)s OFFSET %(offset)s;
    """
    params["limit"] = per_page
    params["offset"] = offset

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(count_sql, params)
            total = cur.fetchone()[0]

            cur.execute(data_sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    # map rows into dicts for clearer template access
    cols = [
        "id", "site", "vlan_id", "network",
        "added_by", "changed_by", "date_update", "date_add",
        "infoblox", "availability"
    ]
    ips = [dict(zip(cols, r)) for r in rows]

    return templates.TemplateResponse(
        "ips.html",
        {
            "request": request,
            "ips": ips,
            "q": q,
            "page": page,
            "per_page": per_page,
            "total": total,
        },
    )
