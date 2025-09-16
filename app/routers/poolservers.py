from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from app.db.database import get_connection  # ← same helper you use elsewhere

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# Columns we’ll show (kept long on purpose; page scrolls horizontally)
COLS = [
    "t_poolservers_id",
    "t_poolservers_equipment_name",
    "t_poolservers_serial_number",
    "t_poolservers_serial_chassis",
    "t_poolservers_date_add",
    "t_poolservers_region",
    "t_poolservers_t_site_id",
    "t_poolservers_priority",
    "t_poolservers_cfi_code",
    "t_poolservers_physical_zone_target",
    "t_poolservers_nic_count",
    "t_poolservers_heartbeat",
    "t_poolservers_san",
    "t_poolservers_bmc",
    "t_poolservers_bmc_last_check_inc",
    "t_poolservers_bmc_date",
    "t_poolservers_bmc_mac",
    "t_poolservers_discovering",
    "t_poolservers_discovering_state",
    "t_poolservers_discovering_date",
    "t_poolservers_discovering_inc",
    "t_poolservers_mynet",
    "t_poolservers_mynet_state",
    "t_poolservers_mynet_date",
    "t_poolservers_mynet_inc",
    "t_poolservers_qualif",
    "t_poolservers_qualif_state",
    "t_poolservers_qualif_date",
    "t_poolservers_t_qualif_id",
    "t_poolservers_business_unit",
    "t_poolservers_ap_code_authorized",
    "t_poolservers_maintenance",
    "t_poolservers_maintenance_comments",
    "t_poolservers_maintenance_date",
    "t_poolservers_mkp_subscription_id",
    "t_poolservers_mkp_owner",
    "t_poolservers_mkp_track_id",
    "t_poolservers_mkp_server_allocated",
    "t_poolservers_mkp_allocation_date",
    "t_poolservers_mkp_ecosystem",
    "t_poolservers_mkp_hostname",
    "t_poolservers_mkp_workspace_id",
    "t_poolservers_mkp_deployment_id",
    "t_poolservers_mkp_product_name",
    "t_poolservers_mkp_product_version",
    "t_poolservers_mkp_component_name",
    "t_poolservers_mkp_component_version",
    "t_poolservers_mkp_product_name_final",
    "t_poolservers_mkp_env",
    "t_poolservers_state_int",
    "t_poolservers_state_string",
    "t_poolservers_supchain_subscription_id",
    "t_poolservers_bmaas_subscription_id",
    "t_poolservers_soki",
    "t_poolservers_bmc_state",
    "t_poolservers_discovering_last_check_inc",
    "t_poolservers_mynet_last_check_inc",
    "t_poolservers_mynet_subscription_id",
]

SELECT_LIST = ", ".join(COLS)


@router.get("/pool_servers", response_class=HTMLResponse)
def page_pool_servers(
    request: Request,
    q: str = Query("", description="Search by serial, equipment, chassis, or CFI"),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
):
    offset = (page - 1) * per_page

    # Build WHERE with ILIKE when q provided
    where = ""
    params = []
    if q:
        where = """
        WHERE
            t_poolservers_equipment_name ILIKE %s
            OR t_poolservers_serial_number ILIKE %s
            OR t_poolservers_serial_chassis ILIKE %s
            OR t_poolservers_cfi_code ILIKE %s
        """
        like = f"%{q}%"
        params.extend([like, like, like, like])

    with get_connection() as conn:
        with conn.cursor() as cur:
            # total
            cur.execute(f"SELECT COUNT(*) FROM supchain.t_poolservers {where}", params)
            total = cur.fetchone()[0]

            # rows
            cur.execute(
                f"""
                SELECT {SELECT_LIST}
                FROM supchain.t_poolservers
                {where}
                ORDER BY t_poolservers_id DESC
                LIMIT %s OFFSET %s
                """,
                params + [per_page, offset],
            )
            rows = cur.fetchall()

    # Convert to list of dicts (easier in Jinja)
    data = [dict(zip(COLS, r)) for r in rows]

    return templates.TemplateResponse(
        "pool_servers.html",
        {
            "request": request,
            "rows": data,
            "page": page,
            "per_page": per_page,
            "total": total,
            "q": q,
            "cols": COLS,
        },
    )
