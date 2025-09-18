from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from app.db.database import get_connection  # same helper you use elsewhere

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Columns where a free-text search actually makes sense
SEARCHABLE_COLS = [
    "t_poolservers_equipment_name",
    "t_poolservers_serial_number",
    "t_poolservers_serial_chassis",
    "t_poolservers_region",
    "t_poolservers_cfi_code",
    "t_poolservers_physical_zone_target",
    "t_poolservers_state_string",
    "t_poolservers_mkp_hostname",
]

# Columns that are booleans (we’ll render Oui/Non badges)
BOOL_COLS = {
    "t_poolservers_heartbeat",
    "t_poolservers_san",
    "t_poolservers_bmc",
    "t_poolservers_discovering",
    "t_poolservers_mynet",
    "t_poolservers_qualif",
    "t_poolservers_maintenance",
    "t_poolservers_mkp_server_allocated",
}

# Optional: columns that are datetimes (pretty formatting)
# If others exist you can add them below without touching the HTML.
DATETIME_COLS = {
    "t_poolservers_date_add",
    "t_poolservers_bmc_date",
    "t_poolservers_discovering_date",
    "t_poolservers_mynet_date",
    "t_poolservers_qualif_date",
    "t_poolservers_maintenance_date",
}

def _prettify(colname: str) -> str:
    """Turn a DB column into a human title."""
    name = colname
    # strip common prefix
    for pref in ("t_poolservers_", "t_"):
        if name.startswith(pref):
            name = name[len(pref):]
            break
    name = name.replace("_", " ").strip()
    # nicer acronyms
    name = (
        name.replace("cfi", "CFI")
            .replace("bmc", "BMC")
            .replace("mac", "MAC")
            .replace("mynet", "MyNet")
            .replace("mkp", "MKP")
            .replace("qualif", "Qualif")
            .replace("nic", "NIC")
            .replace("id", "ID")
    )
    # title case but keep acronyms
    parts = []
    for w in name.split():
        parts.append(w if w.isupper() else w.capitalize())
    return " ".join(parts)

@router.get("/pool_servers", response_class=HTMLResponse)
def pool_servers(
    request: Request,
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
):
    offset = (page - 1) * per_page

    where = ""
    params: list = []
    if q:
        like = f"%{q}%"
        ors = " OR ".join([f'{c} ILIKE %s' for c in SEARCHABLE_COLS])
        where = f"WHERE {ors}"
        params.extend([like] * len(SEARCHABLE_COLS))

    conn = get_connection()
    cur = conn.cursor()

    # total count
    cur.execute(f"SELECT COUNT(*) FROM t_poolservers {where}", params)
    total = cur.fetchone()[0]

    # page rows (select * so we automatically get new cols in the future)
    cur.execute(
        f"""
        SELECT * 
        FROM t_poolservers
        {where}
        ORDER BY t_poolservers_id ASC
        LIMIT %s OFFSET %s
        """,
        params + [per_page, offset],
    )
    rows = cur.fetchall()
    colnames = [c.name for c in cur.description]
    conn.close()

    # format rows in a template-friendly way
    formatted = []
    for row in rows:
        item = {}
        for key, val in zip(colnames, row):
            if key in BOOL_COLS:
                # leave bools as raw True/False; HTML will render badges
                item[key] = bool(val) if val is not None else None
            elif key in DATETIME_COLS and val is not None:
                try:
                    item[key] = val.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    item[key] = str(val)
            else:
                item[key] = val
        formatted.append(item)

    # build pretty headers & a stable column order
    headers = [{"raw": c, "title": _prettify(c)} for c in colnames]

    return templates.TemplateResponse(
        "poolservers.html",
        {
            "request": request,
            "headers": headers,      # [{raw, title}, …]
            "rows": formatted,       # list[dict]
            "page": page,
            "per_page": per_page,
            "total": total,
            "q": q or "",
            "bool_cols": BOOL_COLS,  # for badge rendering
        },
    )
