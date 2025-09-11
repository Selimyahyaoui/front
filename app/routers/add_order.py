# app/routers/add_order.py
from typing import Dict, Any, List
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, PlainTextResponse
from starlette.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime
import os, json

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Single JSON file on the PV for the whole batch
ORDERS_JSON_PATH = Path(os.getenv("ORDERS_JSON_PATH", "/app/uploads/orders.json"))

# ------------- helpers -------------

def _ensure_parent(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)

def _exists_and_nonempty(p: Path) -> bool:
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return isinstance(data, dict) and isinstance(data.get("orders"), list) and len(data["orders"]) > 0
    except Exception:
        # Corrupted file = still considered “in progress” (locked)
        return True

# ------------- UI routes -------------

@router.get("/orders/add", response_class=HTMLResponse)
async def add_order_page(request: Request):
    """
    Renders the form. If a JSON file already exists, page is locked.
    """
    locked = _exists_and_nonempty(ORDERS_JSON_PATH)
    return templates.TemplateResponse(
        "add_order.html",
        {
            "request": request,
            "locked": locked,
            "message_ok": None,
            "message_error": None,
        },
    )

@router.post("/orders/add", response_class=HTMLResponse)
async def add_order_submit(request: Request, json_payload: str = Form(...)):
    """
    Receives orders from the form (hidden JSON field) and writes them to the PV.
    This locks the page until the JSON is deleted via the DELETE API.
    """
    try:
        incoming = json.loads(json_payload)
        orders: List[Dict[str, Any]] = incoming.get("orders", [])
        payload = {
            "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "orders": orders,
        }
        _ensure_parent(ORDERS_JSON_PATH)
        with ORDERS_JSON_PATH.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)

        return templates.TemplateResponse(
            "add_order.html",
            {
                "request": request,
                "locked": True,  # now locked until DELETE is called
                "message_ok": "JSON de commande généré. L’interface est verrouillée jusqu’à suppression via l’API.",
                "message_error": None,
            },
        )
    except Exception as e:
        return templates.TemplateResponse(
            "add_order.html",
            {
                "request": request,
                "locked": _exists_and_nonempty(ORDERS_JSON_PATH),
                "message_ok": None,
                "message_error": f"Erreur: {e}",
            },
        )

# ------------- API: GET / DELETE -------------

@router.get("/orders/json")
async def orders_json_get():
    """
    Returns the current orders.json (404 if not found).
    """
    if not ORDERS_JSON_PATH.exists():
        return JSONResponse({"detail": "Not found"}, status_code=404)
    # You can also stream as JSON; FileResponse keeps it simple
    return FileResponse(path=str(ORDERS_JSON_PATH), media_type="application/json", filename="orders.json")

@router.delete("/orders/json")
async def orders_json_delete():
    """
    Deletes the current orders.json (idempotent).
    """
    try:
        if ORDERS_JSON_PATH.exists():
            ORDERS_JSON_PATH.unlink()
        return PlainTextResponse("", status_code=204)
    except Exception as e:
        return JSONResponse({"detail": f"Delete failed: {e}"}, status_code=500)
