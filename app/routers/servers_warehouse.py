# app/routers/servers_warehouse.py
from typing import List, Dict, Any, Optional, Tuple
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from pathlib import Path
import os, json

from app.db.database import get_connection

router = APIRouter()

# chemin templates absolu pour éviter les soucis d'import
TEMPLATES_DIR = str(Path(__file__).resolve().parents[1] / "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# sortie JSON (sur PVC monté, ex: /app/uploads/servers_selection.json)
SERVERS_JSON_PATH = os.getenv("SERVERS_JSON_PATH", "/app/uploads/servers_selection.json")
POWER_WATTS = [150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 750, 800, 850, 900, 950]

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
        try: probe.unlink()
        except Exception: pass

def fetch_ap_codes() -> List[str]:
    rows = _safe_fetchall("""
        SELECT DISTINCT t_server_sts_t_ap_code_authorized_ap_code
        FROM supchain.t_server_sts
        WHERE t_server_sts_t_ap_code_authorized_ap_code IS NOT NULL
        ORDER BY 1
    """)
    return [r[0] for r in rows if r[0]]

def fetch_physical_zones() -> List[str]:
    # Filtre de disponibilité retiré pour compat DB (on affiche tout)
    rows = _safe_fetchall("""
        SELECT DISTINCT t_physical_zone_target
        FROM supchain.t_physical_zone
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
          s.t_server_sts_country,
          s.t_server_sts_t_ap_code_authorized_ap_code,
          s.t_server_sts_nic_count,
          s.t_server_sts_power_watt,
          s.t_server_sts_heartbeat,
          s.t_server_sts_soki,
          s.t_server_sts_san,
          s.t_server_sts_state_string
        FROM supchain.t_server_sts s
        WHERE s.t_server_sts_state_string = 'warehouse'
        ORDER BY s.t_server_sts_id ASC
    """)
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append({
            "id": r[0],
            "po_number": r[1],
            "vendor": r[2],
            "model": r[3],
            "cfi_code": r[4],
            "country": r[5],
            "ap_code_authorized": r[6],
            "nic_count": r[7],
            "power_watt": r[8],
            "heartbeat": r[9],
            "soki": r[10],
            "san": r[11],
            "state": r[12],
            # Dans t_server_sts il n’y a pas toujours physical_zone_target;
            # si vous l’ajoutez plus tard, mappez-le ici.
            "physical_zone_target": None,
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
        }
    )

@router.post("/servers/warehouse", response_class=HTMLResponse)
async def generate_json(
    request: Request,
    selected_ids: str = Form("")
):
    # Récupère la liste complète pour croiser les champs (simple et robuste)
    servers = { str(s["id"]): s for s in fetch_warehouse_servers() }

    chosen = [sid for sid in (selected_ids.split(",") if selected_ids else []) if sid in servers]
    data: List[Dict[str, Any]] = []

    # Lit tous les champs éditables envoyés par ligne
    form = await request.form()
    for sid in chosen:
        s = servers[sid]
        row = {
            "id": int(sid),
            "poNumber": s["po_number"],
            "vendor": s["vendor"],
            "model": s["model"],
            "cfiCode": s["cfi_code"],
            "country": s["country"],

            "nicCount": int(form.get(f"nic_{sid}", s["nic_count"] or 0) or 0),
            "apCodeAuthorized": form.get(f"ap_{sid}") or s["ap_code_authorized"],
            "physicalZoneTarget": form.get(f"pz_{sid}") or s.get("physical_zone_target"),
            "powerWatt": form.get(f"pw_{sid}") or s["power_watt"],
            "heartBeat": form.get(f"hb_{sid}") or s["heartbeat"],
            "sokiName": form.get(f"soki_{sid}") or s["soki"],
            "san": form.get(f"san_{sid}") or s["san"],
        }
        data.append(row)

    # Écriture JSON sur le PVC
    out = Path(SERVERS_JSON_PATH)
    _ensure_parent_writable(out)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    msg = f"JSON généré ({len(data)} serveurs) → {SERVERS_JSON_PATH}"
    ap_codes = fetch_ap_codes()
    physical_zones = fetch_physical_zones()
    # On ré-affiche la page avec message de succès
    return templates.TemplateResponse(
        "servers_warehouse.html",
        {
            "request": request,
            "message_ok": msg,
            "servers": fetch_warehouse_servers(),
            "ap_codes": ap_codes,
            "physical_zones": physical_zones,
            "power_watts": POWER_WATTS,
        }
    )
