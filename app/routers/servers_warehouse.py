# app/routers/servers_warehouse.py
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime
import os, json, uuid

from app.db.database import get_connection

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

SERVERS_JSON_PATH = os.getenv("SERVERS_JSON_PATH", "/app/uploads/servers_selection.json")
POWER_WATTS = [150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 750, 800, 850, 900, 950]

def _safe_fetchall(sql: str, params: Optional[tuple] = None) -> List[tuple]:
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
        try: probe.unlink()
        except Exception: pass

def fetch_ap_codes() -> List[str]:
    rows = _safe_fetchall("""
        SELECT DISTINCT t_server_sts_t_ap_code_authorized_ap_code
        FROM supchain.t_server_sts
        WHERE t_server_sts_t_ap_code_authorized_ap_code IS NOT NULL
        ORDER BY 1
    """)
    return [r[0] for r in rows]

def fetch_physical_zones() -> List[str]:
    rows = _safe_fetchall("""
        SELECT DISTINCT t_physicalzone_target
        FROM supchain.t_physical_zone
        WHERE t_physicalzone_availability = 'YES'
        ORDER BY 1
    """)
    return [r[0] for r in rows]

def fetch_warehouse_servers() -> List[Dict[str, Any]]:
    rows = _safe_fetchall("""
        SELECT
          s.t_server_sts_id,
          s.t_server_sts_po_number,
          s.t_server_sts_vendor,
          s.t_server_sts_model,
          s.t_server_sts_date_add,
          s.t_server_sts_state_string,
          s.t_server_sts_cfi_code,
          s.t_server_sts_serial,
          s.t_server_sts_country,
          s.t_server_sts_t_ap_code_authorized_ap_code,
          s.t_server_sts_nic_count,
          s.t_server_sts_physical_zone_target,
          s.t_server_sts_power_watt,
          s.t_server_sts_san,
          s.t_server_sts_heartbeat,
          s.t_server_sts_soki
        FROM supchain.t_server_sts s
        WHERE s.t_server_sts_state_string = 'warehouse'
        ORDER BY s.t_server_sts_date_add DESC NULLS LAST, s.t_server_sts_id DESC
    """)
    out = []
    for r in rows:
        out.append({
            "id": r[0],
            "po_number": r[1],
            "vendor": r[2],
            "model": r[3],
            "date_add": r[4],
            "state": r[5],
            "cfi_code": r[6],
            "serial": r[7],
            "country": r[8],
            "ap_code": r[9],
            "nic_count": r[10],
            "physical_zone": r[11],
            "power_watt": r[12],
            "san": r[13],
            "heartbeat": r[14],
            "soki": r[15],
        })
    return out

@router.get("/servers/warehouse", response_class=HTMLResponse)
async def page_warehouse(request: Request):
    return templates.TemplateResponse(
        "servers_warehouse.html",
        {
            "request": request,
            "servers": fetch_warehouse_servers(),
            "ap_codes": fetch_ap_codes(),
            "physical_zones": fetch_physical_zones(),
            "power_watts": POWER_WATTS,
            "message_ok": None,
            "message_error": None,
        },
    )

@router.post("/servers/warehouse", response_class=HTMLResponse)
async def submit_warehouse(
    request: Request,
    selected_ids: Optional[str] = Form(None),  # comma-separated IDs from the template
    # For edited fields we’ll read them dynamically from request.form() in the code below
):
    form = await request.form()
    ids = [int(x) for x in (selected_ids or "").split(",") if x.strip().isdigit()]

    if not ids:
        return templates.TemplateResponse(
            "servers_warehouse.html",
            {
                "request": request,
                "servers": fetch_warehouse_servers(),
                "ap_codes": fetch_ap_codes(),
                "physical_zones": fetch_physical_zones(),
                "power_watts": POWER_WATTS,
                "message_ok": None,
                "message_error": "Aucune ligne sélectionnée.",
            },
            status_code=400,
        )

    # Build JSON list for the selected rows (merge readonly values + edited inputs)
    servers_by_id = {s["id"]: s for s in fetch_warehouse_servers()}
    payload_list = []
    for sid in ids:
        base = servers_by_id.get(sid)
        if not base:
            continue
        # names in the template: ap_code_{id}, physical_zone_{id}, power_watt_{id}, heartbeat_{id}, soki_{id}
        ap_code = form.get(f"ap_code_{sid}") or base.get("ap_code")
        physical_zone = form.get(f"physical_zone_{sid}") or base.get("physical_zone")
        power_watt = form.get(f"power_watt_{sid}") or base.get("power_watt")
        power_watt = int(power_watt) if (power_watt and str(power_watt).isdigit()) else None
        heartbeat = form.get(f"heartbeat_{sid}") or base.get("heartbeat")
        soki = form.get(f"soki_{sid}") or base.get("soki")

        payload_list.append({
            "id": sid,
            "meta": {
                "generatedAt": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "source": "front-interface",
                "type": "server_warehouse",
            },
            "server": {
                "poNumber": base["po_number"],
                "vendor": base["vendor"],
                "model": base["model"],
                "cfiCode": base["cfi_code"],
                "serial": base["serial"],
                "country": base["country"],
                "nicInterfaceNumber": base["nic_count"],
                "apCodeAuthorized": ap_code,
                "physicalZoneTarget": physical_zone,
                "powerWatt": power_watt,
                "san": base["san"],
                "heartBeat": heartbeat,
                "sokiName": soki,
            }
        })

    # Write JSON atomically
    out_path = Path(SERVERS_JSON_PATH)
    try:
        _ensure_parent_writable(out_path)
        tmp_path = out_path.with_name(out_path.stem + f"_{uuid.uuid4().hex}.tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(payload_list, fh, ensure_ascii=False, indent=2)
        tmp_path.replace(out_path)
        message_ok = f"{len(payload_list)} serveur(s) sélectionné(s) → JSON écrit : {out_path}"
        message_error = None
    except Exception as e:
        message_ok = None
        message_error = f"Erreur d’écriture du JSON: {e}"

    return templates.TemplateResponse(
        "servers_warehouse.html",
        {
            "request": request,
            "servers": fetch_warehouse_servers(),
            "ap_codes": fetch_ap_codes(),
            "physical_zones": fetch_physical_zones(),
            "power_watts": POWER_WATTS,
            "message_ok": message_ok,
            "message_error": message_error,
        },
        status_code=200 if message_ok else 500,
    )
