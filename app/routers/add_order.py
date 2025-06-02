from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from datetime import datetime
import os
import json

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

EXPORT_DIR = "app/exports"
os.makedirs(EXPORT_DIR, exist_ok=True)

@router.get("/orders/add", response_class=HTMLResponse)
async def get_add_order(request: Request):
    return templates.TemplateResponse("add_order.html", {"request": request})

@router.post("/orders/add", response_class=HTMLResponse)
async def post_add_order(request: Request, po_number: str = Form(...), order_status: str = Form(...)):
    created_at = datetime.now().isoformat()
    export_data = {
        "po_number": po_number,
        "order_status": order_status,
        "created_at": created_at
    }

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"order_{timestamp}.json"
    filepath = os.path.join(EXPORT_DIR, filename)

    try:
        with open(filepath, "w") as f:
            json.dump(export_data, f, indent=4)
        message = f"✅ Commande enregistrée dans le fichier {filename}"
    except Exception as e:
        message = f"❌ Erreur lors de l'enregistrement : {str(e)}"

    return templates.TemplateResponse("add_order.html", {"request": request, "message": message})
