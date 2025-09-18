from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from app.db.database import get_connection  # your existing helper

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/orders", response_class=HTMLResponse)
def list_orders(
    request: Request,
    q: str | None = Query(None, description="search PO# / project / vendor"),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
):
    offset = (page - 1) * per_page

    # ---- WHERE (shared by count + rows)
    where_sql = ""
    params: list = []
    if q:
        like = f"%{q.lower()}%"
        where_sql = """
        WHERE
            LOWER(s.t_order_servers_po_number)   LIKE %s
         OR LOWER(s.t_order_servers_project_name) LIKE %s
         OR LOWER(s.t_order_servers_vendor)       LIKE %s
        """
        params.extend([like, like, like])

    # ---- SQLs
    count_sql = f"""
        SELECT COUNT(*)
        FROM supchain.t_order_servers s
        {where_sql}
    """

    rows_sql = f"""
        SELECT
            s.t_order_servers_id,
            s.t_order_servers_po_number,
            s.t_order_servers_project_name,
            s.t_order_servers_date_add,
            s.t_order_servers_business_unit,
            s.t_order_servers_vendor,
            s.t_order_servers_status,
            s.t_order_servers_ap_code_authorized,
            EXISTS (
                SELECT 1
                FROM supchain.t_dell_orders d
                WHERE d.purchase_order_id = s.t_order_servers_id
            ) AS has_dell
        FROM supchain.t_order_servers s
        {where_sql}
        ORDER BY s.t_order_servers_date_add DESC, s.t_order_servers_id DESC
        LIMIT %s OFFSET %s
    """

    # ---- DB
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(count_sql, tuple(params))
    total = cur.fetchone()[0]

    cur.execute(rows_sql, tuple(params + [per_page, offset]))
    rows = cur.fetchall()

    conn.close()

    return templates.TemplateResponse(
        "orders.html",
        {
            "request": request,
            "rows": rows,          # <— template will iterate this
            "q": q or "",
            "page": page,
            "per_page": per_page,
            "total": total,
        },
    )
