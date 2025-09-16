from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, Response
from starlette.templating import Jinja2Templates
from pathlib import Path
from typing import Tuple, List
import os
import csv

from app.db.database import get_connection  # <- same helper you already use elsewhere

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# -------- Paths from env (already present in your deployment)
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/uploads"))
ASSETS_JSON_PATH = Path(os.getenv("JSON_OUTPUT_PATH", "/app/uploads/assets_transformed.json"))

# -------- Helpers

def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def is_locked() -> bool:
    """
    Page is locked if the JSON file already exists on the PV.
    """
    try:
        return ASSETS_JSON_PATH.exists() and ASSETS_JSON_PATH.is_file()
    except Exception:
        return False

def _fetch_assets(page: int, per_page: int) -> Tuple[int, List[tuple]]:
    """
    Small preview: show the latest assets at the bottom (no search).
    """
    offset = (page - 1) * per_page
    conn = get_connection()
    cur = conn.cursor()

    # Count
    cur.execute("SELECT COUNT(*) FROM supchain.t_asset_report;")
    total = cur.fetchone()[0]

    # Page rows: pick the most useful columns for the preview
    cur.execute(
        """
        SELECT
          t_asset_report_id,
          t_asset_report_date_add,
          t_asset_report_serial_number,
          t_asset_report_cfi_code,
          t_asset_report_region,
          t_asset_report_cfi_name,
          t_asset_report_customer_number,
          t_asset_report_customer_name,
          t_asset_report_processor_type,
          t_asset_report_number_socket,
          t_asset_report_number_core,
          t_asset_report_model,
          t_asset_report_customer_address,
          t_asset_report_postcode,
          t_asset_report_country,
          t_asset_report_order_number,
          t_asset_report_po_number,
          t_asset_report_bmc_mac_address,
          t_asset_report_memory,
          t_asset_report_hba,
          t_asset_report_boss,
          t_asset_report_perc,
          t_asset_report_nvme,
          t_asset_report_gpu
        FROM supchain.t_asset_report
        ORDER BY t_asset_report_id DESC
        LIMIT %s OFFSET %s
        """,
        (per_page, offset),
    )
    rows = cur.fetchall()
    conn.close()
    return total, rows

# -------- Routes

@router.get("/assets/upload", response_class=HTMLResponse)
def get_assets_upload_page(
    request: Request,
    page: int = 1,
    per_page: int = 10,
):
    total, rows = _fetch_assets(page, per_page)
    return templates.TemplateResponse(
        "assets_upload.html",
        {
            "request": request,
            "page": page,
            "per_page": per_page,
            "total": total,
            "rows": rows,
            "locked": is_locked(),
            "lock_path": str(ASSETS_JSON_PATH),
            "message_ok": None,
            "message_error": None,
        },
    )

@router.post("/assets/upload", response_class=HTMLResponse)
async def post_assets_upload(
    request: Request,
    file: UploadFile = File(...),
    page: int = Form(1),
    per_page: int = Form(10),
):
    # Lock guard (identical logic to Ajout de commande)
    if is_locked():
        total, rows = _fetch_assets(page, per_page)
        return templates.TemplateResponse(
            "assets_upload.html",
            {
                "request": request,
                "page": page,
                "per_page": per_page,
                "total": total,
                "rows": rows,
                "locked": True,
                "lock_path": str(ASSETS_JSON_PATH),
                "message_ok": None,
                "message_error": "Import verrouillé : un lot d’assets est déjà en cours (JSON présent).",
            },
        )

    # Save the uploaded CSV to the PV
    _ensure_dir(UPLOAD_DIR)
    target_csv = UPLOAD_DIR / "assets_upload.csv"
    content = await file.read()
    target_csv.write_bytes(content)

    # (Optional) Quick CSV validation – non-blocking, just to display a small hint
    csv_hint = None
    try:
        with target_csv.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            _ = next(reader, None)  # try read header/first row
            csv_hint = f"Fichier reçu : {file.filename} ({len(content)} octets)."
    except Exception:
        csv_hint = f"Fichier reçu : {file.filename}."

    total, rows = _fetch_assets(page, per_page)
    return templates.TemplateResponse(
        "assets_upload.html",
        {
            "request": request,
            "page": page,
            "per_page": per_page,
            "total": total,
            "rows": rows,
            "locked": False,
            "lock_path": str(ASSETS_JSON_PATH),
            "message_ok": csv_hint or "Fichier uploadé avec succès.",
            "message_error": None,
        },
    )

# ---- JSON control endpoints (same spirit as assets/warehouse pages)

@router.get("/assets/json")
def get_assets_json():
    if ASSETS_JSON_PATH.exists():
        return Response(
            ASSETS_JSON_PATH.read_text(encoding="utf-8"),
            media_type="application/json",
        )
    return Response(status_code=404)

@router.delete("/assets/json")
def delete_assets_json():
    if ASSETS_JSON_PATH.exists():
        ASSETS_JSON_PATH.unlink()
        return {"deleted": str(ASSETS_JSON_PATH)}
    return {"deleted": False, "reason": "not found"}
