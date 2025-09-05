from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from app.db.database import get_connection

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

POWER_WATTS = [150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 750, 800, 850, 900, 950]

# -------------------- Load choices --------------------

def fetch_sites() -> List[Dict[str, Any]]:
    """
    Sites to populate the Site select + country autofill.
    """
    sql = """
        SELECT
          T_Site_Id        AS id,
          T_Site_Location  AS location,
          T_Site_Country   AS country
        FROM supchain.T_Site
        ORDER BY T_Site_Location
    """
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    return [
        {"id": r[0], "location": r[1], "country": r[2], "label": f"{r[1]} ({r[2]})"}
        for r in rows
    ]


def fetch_physical_zones() -> List[str]:
    """
    Preferred: a catalog table (if it exists).
    Fallback: DISTINCT values already present in supchain.t_server_sts.
    """
    with get_connection() as conn, conn.cursor() as cur:
        # Try catalog table (as in the spec)
        try:
            cur.execute("""
                SELECT T_ServerSts_PhysicalZoneTarget
                FROM supchain.T_ServerSts_PhysicalZoneTarget
                WHERE T_PhysicalZone_Availability = 'YES'
                ORDER BY T_ServerSts_PhysicalZoneTarget
            """)
            rows = cur.fetchall()
            if rows:
                return [r[0] for r in rows]
        except Exception:
            pass

        # Fallback on distinct values from main table
        cur.execute("""
            SELECT DISTINCT t_server_sts_physical_zone_target
            FROM supchain.t_server_sts
            WHERE t_server_sts_physical_zone_target IS NOT NULL
            ORDER BY 1
        """)
        rows = cur.fetchall()
        return [r[0] for r in rows]


def fetch_ap_codes() -> List[str]:
    """
    Preferred: T_ApCodeAuthorized.
    Fallback: DISTINCT values from t_server_sts_t_ap_code_authorized_ap_code.
    """
    with get_connection() as conn, conn.cursor() as cur:
        try:
            cur.execute("""
                SELECT T_ApCodeAuthorized_APCODE
                FROM supchain.T_ApCodeAuthorized
                ORDER BY T_ApCodeAuthorized_APCODE
            """)
            rows = cur.fetchall()
            if rows:
                return [r[0] for r in rows]
        except Exception:
            pass

        cur.execute("""
            SELECT DISTINCT t_server_sts_t_ap_code_authorized_ap_code
            FROM supchain.t_server_sts
            WHERE t_server_sts_t_ap_code_authorized_ap_code IS NOT NULL
            ORDER BY 1
        """)
        rows = cur.fetchall()
        return [r[0] for r in rows]


# -------------------- Routes --------------------

@router.get("/orders/add", response_class=HTMLResponse)
async def show_add_order(request: Request):
    sites = fetch_sites()
    physical_zones = fetch_physical_zones()
    ap_codes = fetch_ap_codes()
    return templates.TemplateResponse(
        "add_order.html",
        {
            "request": request,
            "sites": sites,
            "physical_zones": physical_zones,
            "ap_codes": ap_codes,
            "power_watts": POWER_WATTS,
        },
    )


@router.get("/orders/site-info")
async def get_site_info(site_id: int):
    """
    Returns country/location for a given site_id (used by the form via JS).
    """
    sql = """
        SELECT T_Site_Location, T_Site_Country
        FROM supchain.T_Site
        WHERE T_Site_Id = %s
    """
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(sql, (site_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Site introuvable")
        location, country = row
        return {"location": location, "country": country}


@router.post("/orders/add", response_class=HTMLResponse)
async def submit_add_order(
    request: Request,
    po_number: str = Form(...),
    status: str = Form(...),                      # goes to t_server_sts_state_string
    cfi_code: Optional[str] = Form(None),         # t_server_sts_cfi_code
    site_id: int = Form(...),                     # t_site_id
    country: Optional[str] = Form(None),          # t_server_sts_country
    ap_code: Optional[str] = Form(None),          # t_server_sts_t_ap_code_authorized_ap_code
    nic_interface_number: Optional[int] = Form(None),  # t_server_sts_nic_count
    physical_zone: Optional[str] = Form(None),    # t_server_sts_physical_zone_target
    power_watt: Optional[int] = Form(None),       # t_server_sts_power_watt
    san: Optional[str] = Form(None),              # t_server_sts_san
    heartbeat: Optional[str] = Form(None),        # t_server_sts_heartbeat
    soki_name: Optional[str] = Form(None),        # t_server_sts_soki
):
    """
    Inserts a new row in supchain.t_server_sts and shows a JSON preview.
    """
    # Build payload for preview
    order_json = {
        "poNumber": po_number,
        "status": status,
        "cfiCode": cfi_code,
        "site": {"id": site_id, "country": country},
        "apCodeAuthorized": ap_code,
        "nicInterfaceNumber": nic_interface_number,
        "physicalZone": physical_zone,
        "powerWatt": power_watt,
        "san": san,
        "heartBeat": heartbeat,
        "sokiName": soki_name,
    }

    # INSERT in DB (only the columns you showed)
    insert_sql = """
        INSERT INTO supchain.t_server_sts
        (
          t_server_sts_po_number,
          t_server_sts_state_string,
          t_server_sts_cfi_code,
          t_site_id,
          t_server_sts_country,
          t_server_sts_t_ap_code_authorized_ap_code,
          t_server_sts_nic_count,
          t_server_sts_physical_zone_target,
          t_server_sts_power_watt,
          t_server_sts_san,
          t_server_sts_heartbeat,
          t_server_sts_soki
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING t_server_sts_id
    """
    params = (
        po_number,
        status,
        cfi_code,
        site_id,
        country,
        ap_code,
        nic_interface_number,
        physical_zone,
        power_watt,
        san,
        heartbeat,
        soki_name,
    )

    new_id = None
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(insert_sql, params)
            new_id = cur.fetchone()[0]
            conn.commit()
    except Exception as e:
        # Re-render with error message
        sites = fetch_sites()
        physical_zones = fetch_physical_zones()
        ap_codes = fetch_ap_codes()
        return templates.TemplateResponse(
            "add_order.html",
            {
                "request": request,
                "sites": sites,
                "physical_zones": physical_zones,
                "ap_codes": ap_codes,
                "power_watts": POWER_WATTS,
                "message_error": f"Erreur d'insertion: {e}",
                "order_json": order_json,
            },
            status_code=500,
        )

    # Success page with JSON preview
    sites = fetch_sites()
    physical_zones = fetch_physical_zones()
    ap_codes = fetch_ap_codes()
    return templates.TemplateResponse(
        "add_order.html",
        {
            "request": request,
            "sites": sites,
            "physical_zones": physical_zones,
            "ap_codes": ap_codes,
            "power_watts": POWER_WATTS,
            "message_ok": f"Commande enregistrée (ID={new_id}).",
            "order_json": order_json,
        },
    )
