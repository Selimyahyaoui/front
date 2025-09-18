# app/routers/orders.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from app.db import get_connection

router = APIRouter(prefix="/orders", tags=["orders"])
templates = Jinja2Templates(directory="app/templates")


# ---- List Orders (existing page) ----
@router.get("/", response_class=HTMLResponse)
def list_orders(request: Request, q: str = "", page: int = 1, per_page: int = 10):
    offset = (page - 1) * per_page

    # --- build filters ---
    where_sql = ""
    params_count = []
    params_rows = []

    if q:
        where_sql = """
        WHERE LOWER(t_order_servers_po_number) LIKE %s
           OR LOWER(t_order_servers_project_name) LIKE %s
           OR LOWER(t_order_servers_vendor) LIKE %s
        """
        like = f"%{q.lower()}%"
        params_count.extend([like, like, like])
        params_rows.extend([like, like, like])

    # --- count total ---
    count_sql = f"""
        SELECT COUNT(*)
        FROM supchain.t_order_servers
        {where_sql}
    """

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

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(count_sql, tuple(params_count))
    total = cur.fetchone()[0]

    cur.execute(rows_sql, tuple(params_rows + [per_page, offset]))
    rows = cur.fetchall()

    cur.close()
    conn.close()

    return templates.TemplateResponse(
        "orders.html",
        {
            "request": request,
            "rows": rows,
            "q": q,
            "page": page,
            "per_page": per_page,
            "total": total,
        },
    )


# ---- Dell Order Details (new for Jira ticket AER_BMAAS-84) ----
@router.get("/{order_id}/dell", response_class=HTMLResponse)
def dell_detail(request: Request, order_id: int):
    """
    Show linked Dell order details for a given t_order_servers entry.
    """

    conn = get_connection()
    cur = conn.cursor()

    sql = """
        SELECT d.id, d.order_number, d.order_date, d.quote_number,
               d.dell_purchase_id, d.order_status, d.status_datetime,
               p.sku_number, p.description, p.item_quantity, p.line_of_business
        FROM supchain.t_order_servers s
        JOIN supchain.t_dell_orders d
          ON s.t_order_servers_id = d.purchase_order_id
        LEFT JOIN supchain.t_product_info p
          ON d.id = p.dell_order_id
        WHERE s.t_order_servers_id = %s
    """
    cur.execute(sql, (order_id,))
    rows = cur.fetchall()

    cur.close()
    conn.close()

    return templates.TemplateResponse(
        "order_dell_detail.html",
        {
            "request": request,
            "order_id": order_id,
            "rows": rows,
        },
    )
