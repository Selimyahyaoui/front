from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse
import os

router = APIRouter()

JSON_PATH = "app/static/json/assets_transformed.json"

@router.get("/assets/json")
async def get_json_file():
    if not os.path.exists(JSON_PATH):
        return JSONResponse(content={"error": "Fichier JSON introuvable"}, status_code=404)
    return FileResponse(path=JSON_PATH, media_type="application/json", filename="assets_transformed.json")


@router.delete("/assets/json")
async def delete_json_file():
    if os.path.exists(JSON_PATH):
        os.remove(JSON_PATH)
        return JSONResponse(content={"message": "Fichier supprimé avec succès"}, status_code=200)
    else:
        return JSONResponse(content={"error": "Fichier introuvable"}, status_code=404)
