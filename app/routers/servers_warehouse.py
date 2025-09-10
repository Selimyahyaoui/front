# app/routers/servers_warehouse.py
from typing import List, Dict, Any, Optional, Tuple
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime
import os
import json

from app.db.database import get_connection

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Where to write the JSON (PVC is mounted at /app/uploads in your Deployment)
SERVERS_JSON_PATH = os.getenv("SERVERS_JSON_PATH", "/app/uploads/servers_selection.json")

# List for the Power Watt dropdown
POWER_WATTS: List[int] = [150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 750, 800, 850, 900, 950]


# ---------- DB helpers ----------
def _safe_fetchall(sql: str, params: Optional[Tuple] = None) -> List[Tuple]:
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


def fetch_ap_codes() -> List[str]:
    rows = _safe_fetchall(
        """
        SELECT DISTINCT t_server_sts_t_ap_code_authorized_ap_code
        FROM supchain.t_server_sts
        WHERE t_server_sts_t_ap_code_authorized_ap_code IS NOT NULL
        ORDER BY 1
        """
    )
    return [r[0] for r in rows if r[0]]


def fetch_physical_zones() -> List[str]:
    # Show only zones with availability = 'YES'
    rows = _safe_fetchall(
        """
        SELECT DISTINCT t_physical_zone_target
        FROM supchain.t_physical_zone
        WHERE t_physical_zone_date_availability = 'YES'
        ORDER BY 1
        """
    )
    return [r[0] for r in rows if r[0]]


def fetch_warehouse_servers() -> List[Dict[str, Any]]:
    rows = _safe_fetchall(
        """
        SELECT
            s.t_server_sts_id,
            s.t_server_sts_po_number,
            s.t_server_sts_vendor,
            s.t_server_sts_model,
            s.t_server_sts_cfi_code,
            s.t_server_sts_serial,
            s.t_server_sts_country,
            s.t_server_sts_nic_count,
            s.t_server_sts_t_ap_code_authorized_ap_code,
            s.t_server_sts_power_watt,
            s.t_server_sts_heartbeat,
            s.t_server_sts_soki,
            s.t_server_sts_san
        FROM supchain.t_server_sts s
        WHERE lower(trim(s.t_server_sts_state_string)) = 'warehouse'
        ORDER BY s.t_server_sts_id
        """
    )
    cols = [
        "t_server_sts_id",
        "t_server_sts_po_number",
        "t_server_sts_vendor",
        "t_server_sts_model",
        "t_server_sts_cfi_code",
        "t_server_sts_serial",
        "t_server_sts_country",
        "t_server_sts_nic_count",
        "t_server_sts_t_ap_code_authorized_ap_code",
        "t_server_sts_power_watt",
        "t_server_sts_heartbeat",
        "t_server_sts_soki",
        "t_server_sts_san",
    ]
    return [dict(zip(cols, r)) for r in rows]


# ---------- Filesystem helper ----------
def _ensure_parent_writable(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    probe = p.parent / ".write_test"
    try:
        with probe.open("w", encoding="utf-8") as fh:
            fh.write("ok")
    finally:
        try:
            probe.unlink()
        except Exception:
            pass


# ---------- Routes ----------
@router.get("/servers/warehouse", response_class=HTMLResponse)
async def page_warehouse(request: Request):
    servers = fetch_warehouse_servers()
    ap_codes = fetch_ap_codes()
    physical_zones = fetch_physical_zones()
    return templates.TemplateResponse(
        "servers_warehouse.html",
        {
            "request": request,
            "servers": servers,
            "ap_codes": ap_codes,
            "physical_zones": physical_zones,
            "power_watts": POWER_WATTS,
            "message_ok": None,
            "message_error": None,
        },
    )


@router.post("/servers/warehouse", response_class=HTMLResponse)
async def generate_json(request: Request, json_payload: str = Form(...)):
    # Write the payload exactly as sent by the page
    out_path = Path(SERVERS_JSON_PATH)
    try:
        _ensure_parent_writable(out_path)

        # Pretty print for readability
        parsed = json.loads(json_payload)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(parsed, f, indent=2, ensure_ascii=False)

        message_ok = f"JSON généré ({out_path}) à {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        message_error = None
    except Exception as e:
        message_ok = None
        message_error = f"Erreur lors de l'écriture du JSON: {e}"

    # Re-render the page
    servers = fetch_warehouse_servers()
    ap_codes = fetch_ap_codes()
    physical_zones = fetch_physical_zones()
    return templates.TemplateResponse(
        "servers_warehouse.html",
        {
            "request": request,
            "servers": servers,
            "ap_codes": ap_codes,
            "physical_zones": physical_zones,
            "power_watts": POWER_WATTS,
            "message_ok": message_ok,
            "message_error": message_error,
        },
    )
