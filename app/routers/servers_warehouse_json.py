# app/routers/servers_warehouse_json.py
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
import os

router = APIRouter()

SERVERS_JSON_PATH = os.getenv("SERVERS_JSON_PATH", "/app/uploads/servers_selection.json")
SERVERS_JSON = Path(SERVERS_JSON_PATH)

@router.get("/servers/warehouse/json")
async def get_servers_json():
    if not SERVERS_JSON.exists():
        raise HTTPException(status_code=404, detail="Fichier JSON introuvable.")
    return FileResponse(str(SERVERS_JSON), media_type="application/json", filename=SERVERS_JSON.name)

@router.delete("/servers/warehouse/json")
async def delete_servers_json():
    if not SERVERS_JSON.exists():
        raise HTTPException(status_code=404, detail="Fichier JSON introuvable.")
    try:
        SERVERS_JSON.unlink()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Suppression impossible: {e}")
    return JSONResponse({"message": "Fichier supprimé avec succès"})
