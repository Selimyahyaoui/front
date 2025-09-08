# app/routers/add_order.py
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime
import os, json, uuid

from app.db.database import get_connection

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Static list for the "Power Watt" selector
POWER_WATTS = [150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 750, 800, 850, 900, 950]

# Where the generated JSON is stored (mounted PVC path)
ORDER_JSON_PATH = os.getenv("ORDER_JSON_PATH", "/app/uploads/order.json")


# ------------- Safe DB helpers (avoid "current transaction is aborted") -------------

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


# ------------------------------ Lookups (SELECT) ------------------------------

def fetch_sites() -> List[Dict[str, Any]]:
    """
    Sites come from supchain.t_site
      - id: t_site_id
      - location: t_site_location
      - country: t_site_country
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
    rows = _safe_fetchall("""
        SELECT DISTINCT t_server_sts_physical_zone_target
        FROM supchain.t_server_sts
        WHERE t_server_sts_physical_zone_target IS NOT NULL
        ORDER BY 1
    """)
    return [r[0] for r in rows]


def fetch_ap_codes() -> List[str]:
    rows = _safe_fetchall("""
        SELECT DISTINCT t_server_sts_t_ap_code_authorized_ap_code
        FROM supchain.t_server_sts
        WHERE t_server_sts_t_ap_code_authorized_ap_code IS NOT NULL
        ORDER BY 1
    """)
    return [r[0] for r in rows]


# ------------------------------ Utils ------------------------------

def _ensure_parent_writable(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    probe = p.parent / ".write_test"
    try:
        with probe.open("w", encoding="utf-8") as fh:
            fh.write("ok")
    except Exception as e:
        raise RuntimeError(f"Upload directory not writable: {p.parent} ({e})")
    finally:
        try:
            probe.unlink()
        except Exception:
            pass


# ------------------------------ Routes ------------------------------

@router.get("/orders/add", response_class=HTMLResponse)
async def show_add_order(request: Request):
    """
    Render the form with DB-backed dropdowns.
    """
    return templates.TemplateResponse(
        "add_order.html",
        {
            "request": request,
            "sites": fetch_sites(),
            "physical_zones": fetch_physical_zones(),
            "ap_codes": fetch_ap_codes(),
            "power_watts": POWER_WATTS,
        },
    )


@router.get("/orders/site-info")
async def get_site_info(site_id: int):
    """
    Small AJAX endpoint to autofill country when a site is selected.
    """
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
    # --- Form fields (must match your template input names) ---
    po_number: str = Form(...),
    status: str = Form(...),
    cfi_code: Optional[str] = Form(None),

    site_id: int = Form(...),
    country: Optional[str] = Form(None),

    ap_code: Optional[str] = Form(None),
    nic_interface_number: Optional[int] = Form(None),
    physical_zone: Optional[str] = Form(None),

    power_watt: Optional[int] = Form(None),
    san: Optional[str] = Form(None),
    heartbeat: Optional[str] = Form(None),
    soki_name: Optional[str] = Form(None),
):
    """
    Build JSON from the form and store it on the PVC (no DB insert).
    """
    payload = {
        "meta": {
            "id": str(uuid.uuid4()),
            "generatedAt": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "source": "front-interface",
            "type": "order",
        },
        "order": {
            "poNumber": po_number,
            "status": status,
            "cfiCode": cfi_code,
            "site": {"id": site_id, "country": country},
            "network": {
                "nicInterfaceNumber": nic_interface_number,
                "apCodeAuthorized": ap_code,
            },
            "infrastructure": {
                "physicalZoneTarget": physical_zone,
                "powerWatt": power_watt,
                "san": san,
                "heartBeat": heartbeat,
                "sokiName": soki_name,
            },
        },
    }

    out_path = Path(ORDER_JSON_PATH)
    try:
        _ensure_parent_writable(out_path)
        # atomic write
        tmp_path = out_path.with_name(out_path.stem + f"_{uuid.uuid4().hex}.tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        tmp_path.replace(out_path)
        message_ok = f"Fichier JSON généré : {out_path}"
        message_error = None
    except Exception as e:
        message_ok = None
        message_error = f"Erreur d’écriture du JSON: {e}"

    # Re-render with messages + dropdowns again
    return templates.TemplateResponse(
        "add_order.html",
        {
            "request": request,
            "sites": fetch_sites(),
            "physical_zones": fetch_physical_zones(),
            "ap_codes": fetch_ap_codes(),
            "power_watts": POWER_WATTS,
            "message_ok": message_ok,
            "message_error": message_error,
            "order_json": payload if message_ok else None,
        },
        status_code=200 if message_ok else 500,
    )
