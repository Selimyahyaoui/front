from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from app.db.database import get_connection  # same helper you already use

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/assets", response_class=HTMLResponse)
def list_assets(
    request: Request,
    q: str | None = Query(None, description="search serial, CFI, model, PO, client"),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
):
    offset = (page - 1) * per_page

    where = ""
    params: list = []
    if q:
        where = """
        WHERE
            t_asset_report_serial_number ILIKE %s OR
            t_asset_report_cfi_code      ILIKE %s OR
            t_asset_report_model         ILIKE %s OR
            t_asset_report_po_number     ILIKE %s OR
            t_asset_report_customer_name ILIKE %s
        """
        like = f"%{q}%"
        params.extend([like, like, like, like, like])

    # ----- count
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM supchain.t_asset_report {where}", params)
    total = cur.fetchone()[0]

    # ----- page rows
    cur.execute(
        f"""
        SELECT
            t_asset_report_id,
            t_asset_report_date_add,
            t_asset_report_serial_number,
            t_asset_report_cfi_code,
            t_asset_report_region,
            t_asset_report_cfi_name,
            t_asset_report_customer_number,
            t_asset_report_customer_name,
            t_asset_report_processor_type,
            t_asset_report_number_socket,
            t_asset_report_number_core,
            t_asset_report_model,
            t_asset_report_customer_address,
            t_asset_report_postcode,
            t_asset_report_country,
            t_asset_report_order_number,
            t_asset_report_po_number,
            t_asset_report_bmc_mac_address,
            t_asset_report_memory,
            t_asset_report_hba,
            t_asset_report_boss,
            t_asset_report_perc,
            t_asset_report_nvme,
            t_asset_report_gpu,
            t_asset_report_list_hdd_json_format,
            t_asset_report_list_mac_nic_json_format
        FROM supchain.t_asset_report
        {where}
        ORDER BY t_asset_report_id ASC
        LIMIT %s OFFSET %s
        """,
        (*params, per_page, offset),
    )
    rows = cur.fetchall()
    conn.close()

    return templates.TemplateResponse(
        "assets.html",
        {
            "request": request,
            "assets": rows,
            "q": q or "",
            "page": page,
            "per_page": per_page,
            "total": total,
        },
    )
