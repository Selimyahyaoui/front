from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from app.db.database import get_connection  # <- same helper you already use

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/sites", response_class=HTMLResponse)
def list_sites(
    request: Request,
    q: str = Query("", description="search term"),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
):
    """
    List sites from supchain.t_site with search + pagination.
    Search applies (ILIKE) on: id, town, datacenter, sys_id_itsm, address, contact.
    """
    offset = (page - 1) * per_page
    where = ""
    params_total = []
    params_rows = []

    if q:
        where = """
        WHERE
            CAST(t_site_id AS TEXT) ILIKE %s
         OR t_site_town ILIKE %s
         OR t_site_datacenter ILIKE %s
         OR t_site_sys_id_itsm ILIKE %s
         OR t_site_address ILIKE %s
         OR t_site_contact ILIKE %s
        """
        term = f"%{q}%"
        params_total = [term, term, term, term, term, term]
        params_rows = [term, term, term, term, term, term]

    # total
    sql_total = f"SELECT COUNT(*) FROM supchain.t_site {where}"
    # rows
    sql_rows = f"""
        SELECT
            t_site_id,
            t_site_address,
            t_site_country,
            t_site_code_postal,
            t_site_town,
            t_site_sys_id_itsm,
            t_site_contact,
            t_site_region,
            t_site_location,
            t_site_address_cfi,
            t_site_datacenter
        FROM supchain.t_site
        {where}
        ORDER BY t_site_id ASC
        LIMIT %s OFFSET %s
    """

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(sql_total, params_total)
    total = cur.fetchone()[0]

    cur.execute(sql_rows, (*params_rows, per_page, offset))
    rows = cur.fetchall()
    conn.close()

    return templates.TemplateResponse(
        "sites.html",
        {
            "request": request,
            "sites": rows,
            "q": q,
            "page": page,
            "per_page": per_page,
            "total": total,
        },
    )
