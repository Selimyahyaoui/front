from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from app.db.database import get_connection  # same helper you use elsewhere

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Full column list from t_asset_report
COLS = [
    "t_asset_report_id",
    "t_asset_report_date_add",
    "t_asset_report_serial_number",
    "t_asset_report_cfi_code",
    "t_asset_report_region",
    "t_asset_report_cfi_name",
    "t_asset_report_customer_number",
    "t_asset_report_customer_name",
    "t_asset_report_processor_type",
    "t_asset_report_number_socket",
    "t_asset_report_number_core",
    "t_asset_report_model",
    "t_asset_report_customer_address",
    "t_asset_report_postcode",
    "t_asset_report_country",
    "t_asset_report_order_number",
    "t_asset_report_po_number",
    "t_asset_report_bmc_mac_address",
    "t_asset_report_memory",
    "t_asset_report_hba",
    "t_asset_report_boss",
    "t_asset_report_perc",
    "t_asset_report_nvme",
    "t_asset_report_gpu",
    "t_asset_report_list_hdd_json_format",
    "t_asset_report_list_mac_nic_json_format",
]
SELECT_LIST = ", ".join(COLS)

def _rows_to_dicts(rows):
    keys = [
        "id","date_add","serial","cfi_code","region","cfi_name",
        "customer_number","customer_name","cpu","sockets","cores","model",
        "customer_address","postcode","country","order_number","po_number",
        "bmc_mac","memory","hba","boss","perc","nvme","gpu",
        "hdd_json","mac_nic_json",
    ]
    return [{k: r[i] for i, k in enumerate(keys)} for r in rows]

@router.get("/assets", response_class=HTMLResponse)
def list_assets(
    request: Request,
    q: str | None = Query(None, description="Search text"),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
):
    offset = (page - 1) * per_page

    where = ""
    params: list = []
    if q:
        like = f"%{q.strip()}%"
        where = """
        WHERE
            t_asset_report_serial_number ILIKE %s OR
            t_asset_report_cfi_code      ILIKE %s OR
            t_asset_report_model         ILIKE %s OR
            t_asset_report_po_number     ILIKE %s OR
            t_asset_report_customer_name ILIKE %s
        """
        params.extend([like, like, like, like, like])

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM t_asset_report {where}", params)
            total = cur.fetchone()[0]

            cur.execute(
                f"""
                SELECT {SELECT_LIST}
                FROM t_asset_report
                {where}
                ORDER BY t_asset_report_id ASC
                LIMIT %s OFFSET %s
                """,
                params + [per_page, offset],
            )
            rows = cur.fetchall()

    assets = _rows_to_dicts(rows)

    return templates.TemplateResponse(
        "assets.html",
        {
            "request": request,
            "assets": assets,
            "q": q or "",
            "page": page,
            "per_page": per_page,
            "total": total,
        },
    )
