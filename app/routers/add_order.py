# app/routers/add_order.py
from typing import Optional
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from pathlib import Path
import os
import json
import uuid
from datetime import datetime

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

POWER_WATTS = [150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 750, 800, 850, 900, 950]

# ---- Where to store the JSON on the PVC ----
ORDER_JSON_PATH = os.getenv("ORDER_JSON_PATH", "/app/uploads/order.json")

def _ensure_parent_writable(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    probe = p.parent / ".write_test"
    try:
        with probe.open("w") as fh:
            fh.write("ok")
    except Exception as e:
        raise RuntimeError(f"Upload directory not writable: {p.parent} ({e})")
    finally:
        try:
            probe.unlink()
        except Exception:
            pass


@router.get("/orders/add", response_class=HTMLResponse)
async def show_add_order(request: Request):
    """
    Just render the form. (All dropdown data already static for now.)
    """
    return templates.TemplateResponse(
        "add_order.html",
        {
            "request": request,
            "power_watts": POWER_WATTS,
        },
    )


@router.post("/orders/add", response_class=HTMLResponse)
async def submit_add_order(
    request: Request,
    # --- Form fields (names must match your template inputs) ---
    po_number: str = Form(...),
    status: str = Form(...),
    cfi_code: Optional[str] = Form(None),

    site_id: int = Form(...),               # selected site id
    country: Optional[str] = Form(None),    # auto-filled on UI, sent back readonly

    ap_code: Optional[str] = Form(None),
    nic_interface_number: Optional[int] = Form(None),
    physical_zone: Optional[str] = Form(None),

    power_watt: Optional[int] = Form(None),
    san: Optional[str] = Form(None),
    heartbeat: Optional[str] = Form(None),
    soki_name: Optional[str] = Form(None),
):
    """
    Build a JSON payload from the form and store it on the PVC (no DB).
    """
    # JSON structure (adjust keys if your orchestrator expects different names)
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
            "site": {
                "id": site_id,
                "country": country,
            },
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
        # Write atomically (tmp file then move)
        tmp_path = out_path.with_name(out_path.stem + f"_{uuid.uuid4().hex}.tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        tmp_path.replace(out_path)

        message_ok = f"Fichier JSON généré : {out_path}"
        message_error = None
    except Exception as e:
        message_ok = None
        message_error = f"Erreur d’écriture du JSON: {e}"

    # Re-render the same form page with a banner message
    return templates.TemplateResponse(
        "add_order.html",
        {
            "request": request,
            "power_watts": POWER_WATTS,
            "message_ok": message_ok,
            "message_error": message_error,
            "order_json": payload if message_ok else None,
        },
        status_code=200 if message_ok else 500,
    )
