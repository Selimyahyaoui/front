# app/routers/servers_warehouse_json.py
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
import os

router = APIRouter()

JSON_PATH = os.getenv("SERVERS_JSON_PATH", "/app/uploads/servers_selection.json")

@router.get("/servers/json")
async def get_servers_json():
    if not os.path.exists(JSON_PATH):
        raise HTTPException(status_code=404, detail="Fichier JSON introuvable.")
    return FileResponse(JSON_PATH, media_type="application/json", filename="servers_selection.json")

@router.delete("/servers/json")
async def delete_servers_json():
    if not os.path.exists(JSON_PATH):
        raise HTTPException(status_code=404, detail="Fichier JSON introuvable.")
    os.remove(JSON_PATH)
    return JSONResponse({"message": "Fichier supprimé avec succès"})
