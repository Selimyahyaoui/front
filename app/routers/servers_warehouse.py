# app/routers/servers_warehouse.py

from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from pathlib import Path
import os, json

from app.db.database import get_connection

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Où écrire le JSON généré (monté sur ta PVC)
SERVERS_JSON_PATH = Path(os.getenv("SERVERS_JSON_PATH", "/app/uploads/servers_selection.json"))

# Valeurs possibles pour Power Watt (mail)
POWER_WATTS = [150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 750, 800, 850, 900, 950]

# ---------- Helpers SQL ----------
def _safe_fetchall(sql: str, params: Optional[Tuple] = None) -> List[Tuple]:
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

# ---------- Lookups (combos) ----------
def fetch_ap_codes() -> List[str]:
    rows = _safe_fetchall("""
        SELECT DISTINCT t_server_sts_t_ap_code_authorized_ap_code
        FROM supchain.t_server_sts
        WHERE t_server_sts_t_ap_code_authorized_ap_code IS NOT NULL
        ORDER BY 1
    """)
    return [r[0] for r in rows if r[0]]

def fetch_physical_zones() -> List[str]:
    # Filtre de disponibilité = 'YES' (selon photos)
    rows = _safe_fetchall("""
        SELECT DISTINCT t_physical_zone_target
        FROM supchain.t_physical_zone
        WHERE t_physical_zone_date_availability = 'YES'
        ORDER BY 1
    """)
    return [r[0] for r in rows if r[0]]

# ---------- Données tableau ----------
def fetch_warehouse_servers() -> List[Dict[str, Any]]:
    sql = """
    SELECT
        s.t_server_sts_id                                     AS id,
        s.t_server_sts_po_number                              AS po_number,
        s.t_server_sts_vendor                                 AS vendor,
        s.t_server_sts_model                                  AS model,
        s.t_server_sts_cfi_code                               AS cfi_code,
        s.t_server_sts_serial                                 AS serial,
        s.t_server_sts_country                                AS country,
        s.t_server_sts_nic_count                              AS nic_count,
        s.t_server_sts_t_ap_code_authorized_ap_code           AS ap_code_authorized,
        s.t_server_sts_physical_zone_target                   AS physical_zone,
        s.t_server_sts_power_watt                             AS power_watt,
        s.t_server_sts_heartbeat                              AS heartbeat,
        s.t_server_sts_soki                                   AS soki_name,
        s.t_server_sts_san                                    AS san
    FROM supchain.t_server_sts s
    WHERE LOWER(TRIM(s.t_server_sts_state_string)) IN ('warehouse','warehousse','warehous')
    ORDER BY s.t_server_sts_id
    """
    rows = _safe_fetchall(sql)
    cols = [
        "id","po_number","vendor","model","cfi_code","serial","country","nic_count",
        "ap_code_authorized","physical_zone","power_watt","heartbeat","soki_name","san"
    ]
    return [dict(zip(cols, r)) for r in rows]

# ---------- Routes ----------
@router.get("/servers/warehouse", response_class=HTMLResponse)
def page_warehouse(request: Request) -> HTMLResponse:
    servers = fetch_warehouse_servers()
    ap_codes = fetch_ap_codes()
    physical_zones = fetch_physical_zones()

    # Le template attend: servers, ap_codes, physical_zones, power_watts
    ctx = {
        "request": request,
        "servers": servers,
        "ap_codes": ap_codes,
        "physical_zones": physical_zones,
        "power_watts": POWER_WATTS,
        "message_ok": None,
        "message_error": None,
    }
    return templates.TemplateResponse("servers_warehouse.html", ctx)

@router.post("/servers/warehouse", response_class=HTMLResponse)
def generate_json(
    request: Request,
    json_payload: str = Form(...)
) -> HTMLResponse:
    # Écrit le JSON (sélection/valeurs modifiées) sur la PVC
    try:
        data = json.loads(json_payload or "{}")
        _ensure_parent_writable(SERVERS_JSON_PATH)
        with SERVERS_JSON_PATH.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        message_ok = f"JSON généré: {SERVERS_JSON_PATH}"
        message_error = None
    except Exception as e:
        message_ok = None
        message_error = f"Erreur lors de l'écriture du JSON: {e}"

    # Recharger la page avec messages
    servers = fetch_warehouse_servers()
    ap_codes = fetch_ap_codes()
    physical_zones = fetch_physical_zones()
    ctx = {
        "request": request,
        "servers": servers,
        "ap_codes": ap_codes,
        "physical_zones": physical_zones,
        "power_watts": POWER_WATTS,
        "message_ok": message_ok,
        "message_error": message_error,
    }
    return templates.TemplateResponse("servers_warehouse.html", ctx)
