# app/routers/servers_warehouse.py
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.templating import Jinja2Templates
from pathlib import Path
import os, json

from app.db.database import get_connection

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# where we’ll store the JSON for the checked rows
SERVERS_JSON_PATH = os.getenv("SERVERS_JSON_PATH", "/app/uploads/servers_selection.json")

def _safe_fetchall(sql: str, params: Optional[tuple] = None) -> List[tuple]:
    with get_connection() as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            rows = cur.fetchall()
        conn.commit()
        return rows

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
    # Only keep those explicitly marked available
    rows = _safe_fetchall("""
        SELECT DISTINCT t_physical_zone_target
        FROM supchain.t_physical_zone
        WHERE t_physical_zone_date_availability = 'YES'
        ORDER BY 1
    """)
    return [r[0] for r in rows if r[0]]

def fetch_warehouse_servers() -> List[Dict[str, Any]]:
    """
    Keep this deliberately permissive: only filter by state_string='warehouse'.
    LEFT JOIN site just to read the country if present (never filters rows out).
    """
    rows = _safe_fetchall("""
        SELECT
            s.t_server_sts_id,
            s.t_server_sts_po_number,
            s.t_server_sts_vendor,
            s.t_server_sts_model,
            s.t_server_sts_cfi_code,
            s.t_server_sts_serial,
            COALESCE(t.t_site_country, '') AS country,
            COALESCE(s.t_server_sts_nic_count, 0) AS nic_count,
            COALESCE(s.t_server_sts_t_ap_code_authorized_ap_code, '') AS ap_code_authorized,
            ''::text AS physical_zone,          -- edited in UI only
            NULL::integer AS power_watt,        -- edited in UI only
            false AS heartbeat,                 -- edited in UI only
            ''::text AS soki_name,              -- edited in UI only
            false AS san                        -- edited in UI only
        FROM supchain.t_server_sts s
        LEFT JOIN supchain.t_site t
               ON t.t_site_id = s.t_server_sts_t_site_id
        WHERE s.t_server_sts_state_string = 'warehouse'
        ORDER BY s.t_server_sts_id
    """)
    cols = [
        "id","po_number","vendor","model","cfi_code","serial","country",
        "nic_count","ap_code_authorized","physical_zone","power_watt",
        "heartbeat","soki_name","san"
    ]
    return [dict(zip(cols, r)) for r in rows]

@router.get("/servers/warehouse", response_class=HTMLResponse)
async def page_warehouse(request: Request):
    servers = fetch_warehouse_servers()
    physical_zones = fetch_physical_zones()
    ap_codes = fetch_ap_codes()
    return templates.TemplateResponse(
        "servers_warehouse.html",
        {
            "request": request,
            "servers": servers,
            "physical_zones": physical_zones,
            "ap_codes": ap_codes,
            "message_ok": None,
            "message_error": None,
        },
    )

@router.post("/servers/warehouse", response_class=HTMLResponse)
async def post_warehouse(
    request: Request,
    selected_ids: str = Form(""),
    data_payload: str = Form("[]"),  # JSON from the page with edited rows
):
    try:
        items = json.loads(data_payload or "[]")
        out_path = Path(SERVERS_JSON_PATH)
        _ensure_parent_writable(out_path)
        out_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        msg = f"JSON généré ({len(items)} serveurs) → {SERVERS_JSON_PATH}"
        servers = fetch_warehouse_servers()
        physical_zones = fetch_physical_zones()
        ap_codes = fetch_ap_codes()
        return templates.TemplateResponse(
            "servers_warehouse.html",
            {
                "request": request,
                "servers": servers,
                "physical_zones": physical_zones,
                "ap_codes": ap_codes,
                "message_ok": msg,
                "message_error": None,
            },
        )
    except Exception as e:
        servers = fetch_warehouse_servers()
        physical_zones = fetch_physical_zones()
        ap_codes = fetch_ap_codes()
        return templates.TemplateResponse(
            "servers_warehouse.html",
            {
                "request": request,
                "servers": servers,
                "physical_zones": physical_zones,
                "ap_codes": ap_codes,
                "message_ok": None,
                "message_error": f"Erreur : {e}",
            },
        )

# (Optional) tiny debug route to see how many rows the main query returns
@router.get("/servers/warehouse/debug")
async def dbg():
    rows = fetch_warehouse_servers()
    return JSONResponse({"count": len(rows)})
