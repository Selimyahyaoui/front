from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
import os

router = APIRouter()

# Read the same path used by the service (default /tmp…)
JSON_PATH = os.getenv("JSON_OUTPUT_PATH", "/tmp/assets/json/assets_transformed.json")

@router.get("/assets/json")
async def get_json():
    if not os.path.exists(JSON_PATH):
        raise HTTPException(status_code=404, detail="Fichier JSON introuvable.")
    return FileResponse(JSON_PATH, media_type="application/json", filename="assets_transformed.json")

@router.delete("/assets/json")
async def delete_json():
    if not os.path.exists(JSON_PATH):
        raise HTTPException(status_code=404, detail="Fichier JSON introuvable.")
    os.remove(JSON_PATH)
    return JSONResponse({"message": "Fichier supprimé avec succès"})
