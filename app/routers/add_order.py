# app/routers/add_order.py
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from app.db.database import get_connection

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

POWER_WATTS = [150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 750, 800, 850, 900, 950]


# -------------------- Safe DB helpers --------------------

def _safe_fetchall(sql: str, params: Optional[tuple] = None) -> List[tuple]:
    """
    Execute a SELECT and return rows. Ensures rollback on error so we don't
    leave the connection in an aborted transaction state.
    """
    with get_connection() as conn:
        conn.autocommit = False
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                rows = cur.fetchall()
            conn.commit()
            return rows
        except Exception:
            conn.rollback()
            raise


def _safe_fetchone(sql: str, params: Optional[tuple] = None) -> Optional[tuple]:
    with get_connection() as conn:
        conn.autocommit = False
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                row = cur.fetchone()
            conn.commit()
            return row
        except Exception:
            conn.rollback()
            raise


def _safe_insert_returning(sql: str, params: tuple) -> Any:
    """
    Execute an INSERT ... RETURNING and return the first column of the RETURNING row.
    """
    with get_connection() as conn:
        conn.autocommit = False
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                ret = cur.fetchone()
            conn.commit()
            return ret[0] if ret else None
        except Exception:
            conn.rollback()
            raise


# -------------------- Choices / Lookups --------------------

def fetch_sites() -> List[Dict[str, Any]]:
    """
    Sources sites directly from supchain.t_site (lowercase columns as in your schema).
    """
    rows = _safe_fetchall("""
        SELECT
          t_site_id       AS id,
          t_site_location AS location,
          t_site_country  AS country
        FROM supchain.t_site
        ORDER BY t_site_location
    """)
    return [
        {"id": r[0], "location": r[1], "country": r[2], "label": f"{r[1]} ({r[2]})"}
        for r in rows
    ]


def fetch_physical_zones() -> List[str]:
    """
    Use distinct values already present in t_server_sts (robust).
    """
    rows = _safe_fetchall("""
        SELECT DISTINCT t_server_sts_physical_zone_target
        FROM supchain.t_server_sts
        WHERE t_server_sts_physical_zone_target IS NOT NULL
        ORDER BY 1
    """)
    return [r[0] for r in rows]


def fetch_ap_codes() -> List[str]:
    """
    Use distinct values from t_server_sts (no dependency on a catalog table).
    """
    rows = _safe_fetchall("""
        SELECT DISTINCT t_server_sts_t_ap_code_authorized_ap_code
        FROM supchain.t_server_sts
        WHERE t_server_sts_t_ap_code_authorized_ap_code IS NOT NULL
        ORDER BY 1
    """)
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
    row = _safe_fetchone("""
        SELECT t_site_location, t_site_country
        FROM supchain.t_site
        WHERE t_site_id = %s
    """, (site_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Site introuvable")
    location, country = row
    return {"location": location, "country": country}


@router.post("/orders/add", response_class=HTMLResponse)
async def submit_add_order(
    request: Request,
    po_number: str = Form(...),
    status: str = Form(...),                      # -> t_server_sts_state_string
    cfi_code: Optional[str] = Form(None),         # -> t_server_sts_cfi_code
    site_id: int = Form(...),                     # -> t_site_id
    country: Optional[str] = Form(None),          # -> t_server_sts_country
    ap_code: Optional[str] = Form(None),          # -> t_server_sts_t_ap_code_authorized_ap_code
    nic_interface_number: Optional[int] = Form(None),  # -> t_server_sts_nic_count
    physical_zone: Optional[str] = Form(None),    # -> t_server_sts_physical_zone_target
    power_watt: Optional[int] = Form(None),       # -> t_server_sts_power_watt
    san: Optional[str] = Form(None),              # -> t_server_sts_san
    heartbeat: Optional[str] = Form(None),        # -> t_server_sts_heartbeat
    soki_name: Optional[str] = Form(None),        # -> t_server_sts_soki
):
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

    try:
        new_id = _safe_insert_returning(
            """
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
            """,
            (
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
            ),
        )
        message_ok = f"Commande enregistrée (ID={new_id})."
        message_error = None
    except Exception as e:
        message_ok = None
        message_error = f"Erreur d'insertion: {e}"

    # Reload choices for the render (keeps page usable after submit)
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
            "message_ok": message_ok,
            "message_error": message_error,
            "order_json": order_json,
        },
        status_code=200 if message_ok else 500,
    )
