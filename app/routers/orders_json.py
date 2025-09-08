# app/routers/orders_json.py
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
import os

router = APIRouter()

ORDER_JSON_PATH = os.getenv("ORDER_JSON_PATH", "/app/uploads/order.json")
ORDER_JSON = Path(ORDER_JSON_PATH)

@router.get("/orders/json")
async def get_order_json():
    if not ORDER_JSON.exists():
        raise HTTPException(status_code=404, detail="Fichier JSON introuvable.")
    return FileResponse(
        str(ORDER_JSON),
        media_type="application/json",
        filename=ORDER_JSON.name,
    )

@router.delete("/orders/json")
async def delete_order_json():
    if not ORDER_JSON.exists():
        raise HTTPException(status_code=404, detail="Fichier JSON introuvable.")
    try:
        ORDER_JSON.unlink()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Suppression impossible: {e}")
    return JSONResponse({"message": "Fichier supprimé avec succès"})
