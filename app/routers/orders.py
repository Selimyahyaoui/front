# app/routers/orders.py
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from app.db.database import get_connection  # uses your existing helper

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/orders", response_class=HTMLResponse)
def list_orders(
    request: Request,
    q: str | None = "",
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
):
    offset = (page - 1) * per_page

    where_sql = ""
    params_count: list = []
    params_rows: list = []

    if q:
        like = f"%{q.lower()}%"
        where_sql = """
        WHERE
          LOWER(t_order_servers_po_number)    LIKE %s OR
          LOWER(t_order_servers_project_name) LIKE %s OR
          LOWER(t_order_servers_vendor)       LIKE %s
        """
        params_count.extend([like, like, like])
        params_rows.extend([like, like, like])

    count_sql = f"""
      SELECT COUNT(*) FROM supchain.t_order_servers
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
    conn.close()

    return templates.TemplateResponse(
        "orders.html",
        {
            "request": request,
            "rows": rows,
            "q": q or "",
            "page": page,
            "per_page": per_page,
            "total": total,
        },
    )


# ---------- Dell detail (AER_BMAAS-84) with product+assets rows
@router.get("/orders/{order_id}/dell", response_class=HTMLResponse)
def dell_detail(request: Request, order_id: int):
    """
    Show Dell order details linked to t_order_servers row `order_id`.
    Product rows come from t_product_info; asset rows from t_asset_details + t_mac_address.
    """
    conn = get_connection()
    cur = conn.cursor()

    # Header (quote / status / last update) - derive from any linked Dell order
    cur.execute(
        """
        SELECT d.order_number, d.order_date, d.quote_number, d.order_status, d.status_datetime
        FROM supchain.t_order_servers s
        LEFT JOIN supchain.t_dell_orders d ON s.t_order_servers_id = d.purchase_order_id
        WHERE s.t_order_servers_id = %s
        ORDER BY d.status_datetime DESC NULLS LAST, d.id ASC
        LIMIT 1
        """,
        (order_id,),
    )
    header = cur.fetchone()

    # Product rows (one row per product in the Dell order)
    cur.execute(
        """
        SELECT
          d.id          AS dell_id,
          p.id          AS product_id,
          p.sku_number,
          p.description,
          p.item_quantity,
          p.line_of_business
        FROM supchain.t_order_servers s
        LEFT JOIN supchain.t_dell_orders  d ON s.t_order_servers_id = d.purchase_order_id
        LEFT JOIN supchain.t_product_info p ON d.id = p.dell_order_id
        WHERE s.t_order_servers_id = %s
        ORDER BY COALESCE(p.id, 0), d.id
        """,
        (order_id,),
    )
    prod_rows = cur.fetchall()

    # Collect product ids to load assets
    product_ids = [r[1] for r in prod_rows if r[1] is not None]
    assets_by_prod: dict[int, list] = {}

    if product_ids:
        # Build a safe IN clause
        placeholders = ",".join(["%s"] * len(product_ids))
        cur.execute(
            f"""
            SELECT
              a.product_info_id,
              a.service_tag,
              a.asset_tag,
              m.mac_address,
              m.mac_type
            FROM supchain.t_asset_details a
            LEFT JOIN supchain.t_mac_address m ON m.asset_details_id = a.id
            WHERE a.product_info_id IN ({placeholders})
            ORDER BY a.id, m.id
            """,
            tuple(product_ids),
        )

        for pid, service_tag, asset_tag, mac_address, mac_type in cur.fetchall():
            # Start a new asset set when service_tag/asset_tag changes
            lst = assets_by_prod.setdefault(pid, [])
            if not lst or lst[-1].get("service_tag") != service_tag or lst[-1].get("asset_tag") != asset_tag:
                lst.append({"service_tag": service_tag, "asset_tag": asset_tag, "macs": []})
            if mac_address:
                lst[-1]["macs"].append({"mac_address": mac_address, "mac_type": mac_type})

    conn.close()

    # Shape rows for the template: (sku, description, qty, lob, assets_list)
    items = []
    for _dell_id, product_id, sku, desc, qty, lob in prod_rows:
        # Skip pure-null p rows; they happen if there is a Dell order but no product lines
        if product_id is None and sku is None and desc is None and qty is None and lob is None:
            continue
        items.append((sku, desc, qty, lob, assets_by_prod.get(product_id, [])))

    # If we have a Dell header but still no products, show a single placeholder line
    if not items and header:
        items.append((None, None, None, None, []))

    return templates.TemplateResponse(
        "orders_dell.html",
        {
            "request": request,
            "order_id": order_id,
            "header": header,
            "rows": items,  # <— what the template iterates
        },
    )
