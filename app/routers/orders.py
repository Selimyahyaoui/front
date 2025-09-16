from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from app.db.database import get_connection  

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/orders", response_class=HTMLResponse)
def list_orders(
    request: Request,
    q: str = Query("", description="Recherche: PO, projet, vendor"),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
):
    """
    Affiche les commandes depuis supchain.t_order_servers
    (PO, projet, vendor, date, BU, statut, AP code).
    """
    offset = (page - 1) * per_page
    like = f"%{q.lower()}%" if q else None

    # --- Build filters (optional search on po_number / project_name / vendor)
    where_sql = ""
    params_count = []
    params_rows = []

    if q:
        where_sql = """
        WHERE
            LOWER(t_order_servers_po_number) LIKE %s
         OR LOWER(t_order_servers_project_name) LIKE %s
         OR LOWER(t_order_servers_vendor) LIKE %s
        """
        params_count.extend([like, like, like])
        params_rows.extend([like, like, like])

    # --- SQL COUNT
    count_sql = f"""
        SELECT COUNT(*)
        FROM supchain.t_order_servers
        {where_sql}
    """

    # --- SQL rows
    rows_sql = f"""
        SELECT
            t_order_servers_id,
            t_order_servers_po_number,
            t_order_servers_project_name,
            t_order_servers_date_add,
            t_order_servers_business_unit,
            t_order_servers_vendor,
            t_order_servers_status,
            t_order_servers_ap_code_authorized
        FROM supchain.t_order_servers
        {where_sql}
        ORDER BY t_order_servers_date_add DESC, t_order_servers_id DESC
        LIMIT %s OFFSET %s
    """

    # --- DB
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(count_sql, tuple(params_count))
    total = cur.fetchone()[0]

    cur.execute(rows_sql, tuple(params_rows + [per_page, offset]))
    rows = cur.fetchall()

    conn.close()

    return templates.TemplateResponse(
        "orders.html",
        {
            "request": request,
            "orders": rows,
            "q": q,
            "page": page,
            "per_page": per_page,
            "total": total,
        },
    )
