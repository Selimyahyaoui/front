from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from app.db.database import get_connection  # your existing helper

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/orders", response_class=HTMLResponse)
def list_orders(
    request: Request,
    q: str | None = Query(None, description="Rechercher po, projet, vendor"),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
):
    """
    Listing basé sur supchain.t_order_servers + flag 'has_dell'
    s'il existe des lignes correspondantes dans supchain.t_dell_orders.
    """
    offset = (page - 1) * per_page

    where_sql = ""
    params_count: list = []
    params_rows: list = []

    if q:
        where_sql = """
        WHERE
            LOWER(t_order_servers_po_number)       LIKE %s
         OR LOWER(t_order_servers_project_name)    LIKE %s
         OR LOWER(t_order_servers_vendor)          LIKE %s
        """
        like = f"%{q.lower()}%"
        params_count.extend([like, like, like])
        params_rows.extend([like, like, like])

    count_sql = f"""
        SELECT COUNT(*) FROM supchain.t_order_servers
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

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(count_sql, tuple(params_count))
        total = cur.fetchone()[0]

        cur.execute(rows_sql, tuple(params_rows + [per_page, offset]))
        rows = cur.fetchall()

    return templates.TemplateResponse(
        "orders.html",
        {"request": request, "rows": rows, "page": page,
         "per_page": per_page, "total": total, "q": q or ""},
    )


@router.get("/orders/{order_id}/dell", response_class=HTMLResponse)
def dell_order_detail(order_id: int, request: Request):
    """
    Page de détail Dell :
      - Récap de la commande (t_order_servers)
      - Dernier statut Dell (t_dell_orders : max(status_datetime))
      - Lignes de produits (t_product_info) pour ce dell_order_id
    """
    with get_connection() as conn:
        cur = conn.cursor()

        # header from t_order_servers
        cur.execute(
            """
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
            WHERE t_order_servers_id = %s
            """,
            (order_id,),
        )
        header = cur.fetchone()
        if not header:
            raise HTTPException(status_code=404, detail="Commande inconnue")

        # latest dell order row for this purchase_order_id
        cur.execute(
            """
            SELECT id, order_number, order_date, quote_number,
                   dell_purchase_id, order_status, status_datetime
            FROM supchain.t_dell_orders
            WHERE purchase_order_id = %s
            ORDER BY status_datetime DESC NULLS LAST, id DESC
            LIMIT 1
            """,
            (order_id,),
        )
        dell = cur.fetchone()

        items = []
        if dell:
            dell_order_id = dell[0]
            cur.execute(
                """
                SELECT sku_number, description, item_quantity, line_of_business
                FROM supchain.t_product_info
                WHERE dell_order_id = %s
                ORDER BY id ASC
                """,
                (dell_order_id,),
            )
            items = cur.fetchall()

    return templates.TemplateResponse(
        "orders_dell.html",
        {"request": request, "header": header, "dell": dell, "items": items},
    )
