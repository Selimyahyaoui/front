# app/routers/servers_warehouse.py
from typing import List, Dict, Any, Optional, Tuple
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from pathlib import Path
import os, json

from app.db.database import get_connection

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Où écrire le JSON final (PV monté sur /app/uploads)
SERVERS_JSON_PATH = os.getenv("SERVERS_JSON_PATH", "/app/uploads/servers_selection.json")
# Liste fixe (spécifications)
POWER_WATTS = [150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 750, 800, 850, 900, 950]


# --- utils DB ---------------------------------------------------------------

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
    # test d'écriture
    probe = p.parent / "_write_test"
    try:
        with probe.open("w", encoding="utf-8") as fh:
            fh.write("ok")
    finally:
        try:
            probe.unlink()
        except Exception:
            pass


# --- queries pour remplir les listes ---------------------------------------

def fetch_ap_codes() -> List[str]:
    # Distinct des codes AP existants côté serveurs (non null)
    rows = _safe_fetchall("""
        SELECT DISTINCT t_server_sts_t_ap_code_authorized_ap_code
        FROM supchain.t_server_sts
        WHERE t_server_sts_t_ap_code_authorized_ap_code IS NOT NULL
        ORDER BY 1
    """)
    return [r[0] for r in rows if r[0]]


def fetch_physical_zones() -> List[str]:
    # SEULEMENT les zones disponibles
    rows = _safe_fetchall("""
        SELECT DISTINCT t_physical_zone_target
        FROM supchain.t_physical_zone
        WHERE t_physical_zone_date_availability = 'YES'
        ORDER BY 1
    """)
    return [r[0] for r in rows if r[0]]


def fetch_warehouse_servers() -> List[Dict[str, Any]]:
    # Serveurs en stock (state_string = 'warehouse'), avec pays du site si dispo
    rows = _safe_fetchall("""
        SELECT
            s.t_server_sts_id,
            s.t_server_sts_po_number,
            s.t_server_sts_vendor,
            s.t_server_sts_model,
            s.t_server_sts_serial,
            s.t_server_sts_cfi_code,
            COALESCE(cty.t_site_country, '') AS country,
            s.t_server_sts_t_ap_code_authorized_ap_code AS ap_code,
            s.t_server_sts_nic_count,
            s.t_server_sts_state_string
        FROM supchain.t_server_sts s
        LEFT JOIN supchain.t_site cty
               ON cty.t_site_id = s.t_server_sts_t_site_id
        WHERE s.t_server_sts_state_string = 'warehouse'
        ORDER BY s.t_server_sts_id ASC
    """)
    out = []
    for r in rows:
        out.append({
            "id": r[0],
            "po_number": r[1] or "",
            "vendor": r[2] or "",
            "model": r[3] or "",
            "serial": r[4] or "",
            "cfi_code": r[5] or "",
            "country": r[6] or "",
            "ap_code": r[7] or "",
            "nic_count": r[8] or 0,
        })
    return out


# --- routes ----------------------------------------------------------------

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
async def post_warehouse(
    request: Request,
    selected_ids: str = Form(""),
    # les champs par ligne arrivent sous forme xxx_<id>; on traite dans le code
):
    try:
        form = await request.form()
        ids = [x for x in (selected_ids or "").split(",") if x.strip()]
        results: List[Dict[str, Any]] = []

        for sid in ids:
            def gv(name: str, default=""):
                return form.get(f"{name}_{sid}", default)

            # Reconstruction de la ligne éditée
            item = {
                "id": int(sid),
                "po_number": gv("po_number"),
                "vendor": gv("vendor"),
                "model": gv("model"),
                "cfi_code": gv("cfi_code"),
                "serial": gv("serial"),
                "country": gv("country"),
                "nic_count": int(gv("nic_count", "0") or 0),
                "ap_code_authorized": gv("ap_code"),
                "physical_zone_target": gv("physical_zone"),
                "power_watt": int(gv("power_watt", "0") or 0),
                "heartbeat": gv("heartbeat", "") == "on",
                "soki_name": gv("soki_name"),
                "san": gv("san", "") == "on",
            }
            results.append(item)

        # Ecriture JSON
        out_path = Path(SERVERS_JSON_PATH)
        _ensure_parent_writable(out_path)
        with out_path.open("w", encoding="utf-8") as fh:
            json.dump(results, fh, ensure_ascii=False, indent=2)

        msg_ok = f"JSON généré ({len(results)} serveur(s)) → {out_path}"
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
                "message_ok": msg_ok,
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
                "message_error": f"Erreur : {e}",
            },
        )
