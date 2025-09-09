# app/routers/servers_warehouse.py
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from pathlib import Path
import os, json

from app.db.database import get_connection

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Where we store the JSON to be consumed by your orchestrator (PVC mounted path)
SERVERS_JSON_PATH = Path(os.getenv("SERVERS_JSON_PATH", "/app/uploads/servers_selection.json"))

POWER_WATTS = [150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 650, 700, 750, 800, 850, 900, 950]


# ---------- small DB helpers ----------
def _safe_fetchall(sql: str, params: Optional[tuple] = None) -> List[tuple]:
    with get_connection() as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            rows = cur.fetchall()
        conn.commit()
        return rows


def fetch_ap_codes() -> List[str]:
    sql = """
    SELECT DISTINCT t_server_sts_t_ap_code_authorized_ap_code
    FROM supchain.t_server_sts
    WHERE t_server_sts_t_ap_code_authorized_ap_code IS NOT NULL
    ORDER BY 1
    """
    return [r[0] for r in _safe_fetchall(sql)]


def fetch_physical_zones() -> List[str]:
    # Only zones explicitly available
    sql = """
    SELECT DISTINCT t_physical_zone_target
    FROM supchain.t_physical_zone
    WHERE t_physical_zone_date_availability = 'YES'
    ORDER BY 1
    """
    return [r[0] for r in _safe_fetchall(sql)]


def fetch_warehouse_servers() -> List[Dict[str, Any]]:
    sql = """
    SELECT
        s.t_server_sts_id,
        s.t_server_sts_po_number,
        s.t_server_sts_vendor,
        s.t_server_sts_model,
        s.t_server_sts_serial,
        s.t_server_sts_cfi_code,
        s.t_server_sts_country,
        s.t_server_sts_t_ap_code_authorized_ap_code,
        s.t_server_sts_nic_count
    FROM supchain.t_server_sts AS s
    WHERE LOWER(TRIM(s.t_server_sts_state_string)) = 'warehouse'
    ORDER BY s.t_server_sts_id
    """
    rows = _safe_fetchall(sql)
    cols = [
        "t_server_sts_id",
        "t_server_sts_po_number",
        "t_server_sts_vendor",
        "t_server_sts_model",
        "t_server_sts_serial",
        "t_server_sts_cfi_code",
        "t_server_sts_country",
        "t_server_sts_t_ap_code_authorized_ap_code",
        "t_server_sts_nic_count",
    ]
    return [dict(zip(cols, r)) for r in rows]


def _ensure_parent_writable(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    probe = p.parent / "._write_test"
    with probe.open("w", encoding="utf-8") as fh:
        fh.write("ok")
    probe.unlink(missing_ok=True)


# ---------- routes ----------
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
async def generate_warehouse_json(
    request: Request,
    json_payload: str = Form(...),
):
    """
    Receives the hidden 'json_payload' (a JSON string built in the page)
    and writes it to SERVERS_JSON_PATH.
    """
    try:
        data = json.loads(json_payload)
        _ensure_parent_writable(SERVERS_JSON_PATH)
        with SERVERS_JSON_PATH.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)

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
                "message_ok": f"JSON généré: {SERVERS_JSON_PATH}",
                "message_error": None,
            },
        )
    except Exception as e:
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
                "message_error": f"Erreur: {e}",
            },
        )
