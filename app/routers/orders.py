# app/routers/orders.py
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from app.db.database import get_connection  # tu gardes ton helper

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
          LOWER(t_order_servers_po_number)   LIKE %s OR
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
        {
            "request": request,
            "rows": rows,
            "q": q or "",
            "page": page,
            "per_page": per_page,
            "total": total,
        },
    )


# ---------- Dell detail (AER_BMAAS-84) avec assets et mac addresses
@router.get("/orders/{order_id}/dell", response_class=HTMLResponse)
def dell_detail(request: Request, order_id: int):
    conn = get_connection()
    cur = conn.cursor()

    # 1) Header Dell Orders + Produits
    sql = """
      SELECT
        d.id, d.order_number, d.order_date, d.quote_number,
        d.dell_purchase_id, d.order_status, d.status_datetime,
        p.id as product_id, p.sku_number, p.description, 
        p.item_quantity, p.line_of_business
      FROM supchain.t_order_servers s
      LEFT JOIN supchain.t_dell_orders   d ON s.t_order_servers_id = d.purchase_order_id
      LEFT JOIN supchain.t_product_info  p ON d.id = p.dell_order_id
      WHERE s.t_order_servers_id = %s
      ORDER BY d.id NULLS LAST
    """
    cur.execute(sql, (order_id,))
    rows = cur.fetchall()

    # 2) Si pas de données
    if not rows:
        conn.close()
        return templates.TemplateResponse(
            "orders_dell.html",
            {"request": request, "order_id": order_id, "rows": [], "header": None},
        )

    # 3) Construire le header
    (d_id, order_number, order_date, quote_number,
     dell_purchase_id, order_status, status_datetime,
     *_rest) = rows[0]
    header = {
        "order_number": order_number,
        "order_date": order_date,
        "quote_number": quote_number,
        "order_status": order_status,
        "status_datetime": status_datetime,
    }

    # 4) Construire dict produits
    products = []
    prod_ids = []
    for r in rows:
        (
            d_id, order_number, order_date, quote_number,
            dell_purchase_id, order_status, status_datetime,
            product_id, sku, descr, qty, lob
        ) = r

        if product_id:
            products.append({
                "id": product_id,
                "sku": sku,
                "description": descr,
                "qty": qty,
                "lob": lob,
                "assets": []
            })
            prod_ids.append(product_id)

    # 5) Charger les assets liés
    assets_by_prod = {}
    if prod_ids:
        cur.execute(
            f"""
            SELECT id, product_info_id, service_tag, asset_tag
            FROM supchain.t_asset_details
            WHERE product_info_id = ANY(%s)
            """,
            (prod_ids,)
        )
        for aid, prod_id, service_tag, asset_tag in cur.fetchall():
            asset = {"id": aid, "service_tag": service_tag, "asset_tag": asset_tag, "macs": []}
            assets_by_prod.setdefault(prod_id, []).append(asset)

    # 6) Charger les MACs liés
    asset_ids = [a["id"] for assets in assets_by_prod.values() for a in assets]
    if asset_ids:
        cur.execute(
            f"""
            SELECT id, asset_details_id, mac_address, mac_type
            FROM supchain.t_mac_address
            WHERE asset_details_id = ANY(%s)
            """,
            (asset_ids,)
        )
        for _mid, asset_details_id, mac_address, mac_type in cur.fetchall():
            for assets in assets_by_prod.values():
                for a in assets:
                    if a["id"] == asset_details_id:
                        a["macs"].append({"mac_address": mac_address, "mac_type": mac_type})

    # rattacher assets aux produits
    for p in products:
        if p["id"] in assets_by_prod:
            p["assets"] = assets_by_prod[p["id"]]

    cur.close()
    conn.close()

    return templates.TemplateResponse(
        "orders_dell.html",
        {
            "request": request,
            "order_id": order_id,
            "rows": rows,
            "header": header,
            "products": products,
        },
    )
