# app/routers/orders.py
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from app.db.database import get_connection

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
    conn.close()

    return templates.TemplateResponse(
        "orders.html",
        {"request": request, "rows": rows, "q": q or "", "page": page, "per_page": per_page, "total": total},
    )


@router.get("/orders/{order_id}/dell", response_class=HTMLResponse)
def dell_detail(request: Request, order_id: int):
    """
    Read-only detail page:
    t_order_servers -> t_dell_orders -> t_product_info
                                    -> t_asset_details (via product_info_id)
                                    -> t_mac_address  (via asset_details_id)
    """

    conn = get_connection()
    cur = conn.cursor()

    # Top header (same as before)
    head_sql = """
      SELECT
        d.order_number, d.order_date, d.quote_number, d.order_status, d.status_datetime
      FROM supchain.t_order_servers s
      LEFT JOIN supchain.t_dell_orders d
        ON s.t_order_servers_id = d.purchase_order_id
      WHERE s.t_order_servers_id = %s
      ORDER BY d.id NULLS LAST
      LIMIT 1
    """
    cur.execute(head_sql, (order_id,))
    header = cur.fetchone()

    # Flat rows for product + asset + mac + **product's dell status**
    rows_sql = """
      SELECT
        p.id, p.sku_number, p.description, p.item_quantity, p.line_of_business,
        d.order_status, d.status_datetime,               -- << added
        ad.id, ad.service_tag, ad.asset_tag,
        ma.mac_address, ma.mac_type
      FROM supchain.t_order_servers s
      LEFT JOIN supchain.t_dell_orders d
        ON s.t_order_servers_id = d.purchase_order_id
      LEFT JOIN supchain.t_product_info p
        ON d.id = p.dell_order_id
      LEFT JOIN supchain.t_asset_details ad
        ON ad.product_info_id = p.id
      LEFT JOIN supchain.t_mac_address ma
        ON ma.asset_details_id = ad.id
      WHERE s.t_order_servers_id = %s
      ORDER BY p.id NULLS LAST, ad.id NULLS LAST, ma.id NULLS LAST
    """
    cur.execute(rows_sql, (order_id,))
    flat_rows = cur.fetchall()
    conn.close()

    # Build nested structure with per-product status
    products_map: dict[int, dict] = {}
    for (pid, sku, desc, qty, lob,
         p_status, p_status_dt,
         aid, service_tag, asset_tag,
         mac_addr, mac_type) in flat_rows:

        if pid is None:
            continue

        prod = products_map.setdefault(pid, {
            "product_id": pid,
            "sku": sku or "",
            "description": desc or "",
            "qty": qty or 0,
            "lob": lob or "",
            "status": p_status or "",          # << keep status per product
            "status_dt": p_status_dt,          # optional
            "assets": {}
        })

        if aid:
            asset = prod["assets"].setdefault(aid, {
                "asset_id": aid,
                "service_tag": service_tag or "",
                "asset_tag": asset_tag or "",
                "macs": []
            })
            if mac_addr:
                asset["macs"].append({"mac_address": mac_addr, "mac_type": mac_type or ""})

    products = []
    for prod in products_map.values():
        prod["assets"] = list(prod["assets"].values())
        products.append(prod)

    return templates.TemplateResponse(
        "orders_dell.html",
        {
            "request": request,
            "order_id": order_id,
            "header": header,      # (order_number, order_date, quote, status, status_datetime)
            "products": products,  # each has .status now
        },
    )
