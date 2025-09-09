# app/routers/servers_warehouse.py
from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.templating import Jinja2Templates
from pathlib import Path
import os, json

from app.db.database import get_connection  # <- your existing helper

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# where we store the JSON created from selected rows
SERVERS_JSON_PATH = Path(os.getenv("SERVERS_JSON_PATH", "/app/uploads/servers_selection.json"))

POWER_WATTS = [150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 650, 700, 750, 800, 850, 900, 950]

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

def fetch_ap_codes() -> List[str]:
    rows = _safe_fetchall("""
        SELECT DISTINCT t_server_sts_t_ap_code_authorized_ap_code
        FROM supchain.t_server_sts
        WHERE t_server_sts_t_ap_code_authorized_ap_code IS NOT NULL
        ORDER BY 1
    """)
    return [r[0] for r in rows if r[0]]

def fetch_physical_zones() -> List[str]:
    # Only zones with availability = 'YES'
    rows = _safe_fetchall("""
        SELECT DISTINCT t_physical_zone_target
        FROM supchain.t_physical_zone
        WHERE t_physical_zone_date_availability = 'YES'
        ORDER BY 1
    """)
    return [r[0] for r in rows if r[0]]

def fetch_warehouse_servers() -> List[Dict[str, Any]]:
    rows = _safe_fetchall("""
        SELECT
            s.t_server_sts_id,
            s.t_server_sts_po_number,
            s.t_server_sts_vendor,
            s.t_server_sts_model,
            s.t_server_sts_cfi_code,
            s.t_server_sts_serial,
            COALESCE(si.t_site_country,'') AS country,
            COALESCE(s.t_server_sts_nic_count, 0) AS nic_count,
            COALESCE(s.t_server_sts_t_ap_code_authorized_ap_code, '') AS ap_code,
            ''::text AS physical_zone,        -- editable on screen only
            NULL::int AS power_watt,          -- editable on screen only
            ''::text AS heartbeat,            -- editable on screen only
            ''::text AS soki_name,            -- editable on screen only
            ''::text AS san                   -- editable on screen only
        FROM supchain.t_server_sts s
        LEFT JOIN supchain.t_site si ON si.t_site_id = s.t_server_sts_t_site_id
        WHERE lower(trim(s.t_server_sts_state_string)) = 'warehouse'
        ORDER BY s.t_server_sts_id ASC
    """)
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append({
            "id": r[0],
            "po_number": r[1] or "",
            "vendor": r[2] or "",
            "model": r[3] or "",
            "cfi_code": r[4] or "",
            "serial": r[5] or "",
            "country": r[6] or "",
            "nic_count": int(r[7]) if r[7] is not None else 0,
            "ap_code": r[8] or "",
            "physical_zone": r[9] or "",
            "power_watt": r[10],
            "heartbeat": r[11] or "",
            "soki_name": r[12] or "",
            "san": r[13] or "",
        })
    return out

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

@router.post("/servers/warehouse/json", response_class=HTMLResponse)
async def create_json(request: Request, payload: str = Form(...)):
    """
    Receives a hidden 'payload' field containing a JSON array of the selected rows
    with the edited values. Writes it to SERVERS_JSON_PATH.
    """
    try:
        data = json.loads(payload)
        _ensure_parent_writable(SERVERS_JSON_PATH)
        SERVERS_JSON_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return JSONResponse({"ok": True, "path": str(SERVERS_JSON_PATH)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})
