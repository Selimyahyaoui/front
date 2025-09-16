from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from app.db.database import get_connection

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/vlans", response_class=HTMLResponse)
def list_vlans(
    request: Request,
    q: str | None = Query(None, description="search text"),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
):
    offset = (page - 1) * per_page

    where = []
    params: list = []

    if q:
        like = f"%{q}%"
        where.append("""
            (
                CAST(t_ref_set_vlan_id AS TEXT) ILIKE %s OR
                t_ref_set_vlan_vlan_target ILIKE %s OR
                CAST(t_ref_set_vlan_vlan_id AS TEXT) ILIKE %s OR
                t_ref_set_vlan_physical_zone ILIKE %s OR
                t_ref_set_vlan_environnement ILIKE %s OR
                t_ref_set_vlan_scope_info_blox ILIKE %s
            )
        """)
        params += [like, like, like, like, like, like]

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    # total count
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM supchain.t_ref_set_vlan {where_sql}", params)
            total = cur.fetchone()[0]

            sql = f"""
                SELECT
                  t_ref_set_vlan_id,
                  t_ref_set_vlan_date_time_added,
                  t_ref_set_vlan_vlan_target,
                  t_ref_set_vlan_comments,
                  t_ref_set_vlan_vlan_id,
                  t_ref_set_vlan_physical_zone,
                  t_ref_set_vlan_environnement,
                  t_ref_set_vlan_trunked,
                  t_ref_set_vlan_natif,
                  t_ref_set_vlan_lacp,
                  t_ref_set_vlan_scope_info_blox,
                  t_ref_set_vlan_t_ap_code_authorized_id,
                  t_ref_set_vlan_scope_info_blox_mkp
                FROM supchain.t_ref_set_vlan
                {where_sql}
                ORDER BY t_ref_set_vlan_id ASC
                LIMIT %s OFFSET %s
            """
            cur.execute(sql, params + [per_page, offset])
            rows = cur.fetchall()

    return templates.TemplateResponse(
        "vlans.html",
        {
            "request": request,
            "vlans": rows,
            "q": q or "",
            "page": page,
            "per_page": per_page,
            "total": total,
        },
    )
