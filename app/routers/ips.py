# app/routers/ips.py
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from app.db.database import get_connection  # your existing helper

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/ips", response_class=HTMLResponse)
def list_ips(
    request: Request,
    q: str | None = "",
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
):
    """
    List t_ref_dhcp (parent). Each row can expand to show child rows from t_result_dhcp.
    """
    offset = (page - 1) * per_page

    # Optional search on some parent fields (LOWER for case-insensitive)
    where_sql = ""
    params_count: list = []
    params_rows: list = []

    if q:
        like = f"%{q.lower()}%"
        where_sql = """
        WHERE
          LOWER(CAST(t_ref_dhcp_id AS TEXT))   LIKE %s OR
          LOWER(CAST(t_ref_dhcp_t_site AS TEXT)) LIKE %s OR
          LOWER(CAST(t_ref_dhcp_id_lan AS TEXT)) LIKE %s OR
          LOWER(t_ref_dhcp_network)            LIKE %s OR
          LOWER(CAST(t_ref_dhcp_infoblox AS TEXT)) LIKE %s
        """
        params_count.extend([like, like, like, like, like])
        params_rows.extend([like, like, like, like, like])

    # Count parents
    count_sql = f"""
      SELECT COUNT(*)
      FROM supchain.t_ref_dhcp
      {where_sql}
    """

    # Fetch page of parents
    rows_sql = f"""
      SELECT
        t_ref_dhcp_id,
        t_ref_dhcp_t_site,
        t_ref_dhcp_id_lan,
        t_ref_dhcp_network,
        t_ref_dhcp_add_by,
        t_ref_dhcp_change_by,
        t_ref_dhcp_date_add,
        t_ref_dhcp_date_update,
        t_ref_dhcp_infoblox,
        t_ref_dhcp_availability
      FROM supchain.t_ref_dhcp
      {where_sql}
      ORDER BY t_ref_dhcp_id DESC
      LIMIT %s OFFSET %s
    """

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(count_sql, tuple(params_count))
    total = cur.fetchone()[0]

    cur.execute(rows_sql, tuple(params_rows + [per_page, offset]))
    parent_rows = cur.fetchall()

    # Build children map: { ref_dhcp_id: [ ...child rows... ] }
    children_map: dict[int, list] = {}
    parent_ids = [r[0] for r in parent_rows]
    if parent_ids:
        # Build an IN %(tuple)s safely
        # psycopg2 doesn't expand %s for tuples unless we use IN %s with tuple
        sql_children = """
          SELECT
            t_result_dhcp_id_ref_dhcp,
            t_result_dhcp_id,
            t_result_dhcp_host_a,
            t_result_dhcp_ip,
            t_result_dhcp_mac_address,
            t_result_dhcp_date_add,
            t_result_dhcp_date_update
          FROM supchain.t_result_dhcp
          WHERE t_result_dhcp_id_ref_dhcp = ANY(%s)
          ORDER BY t_result_dhcp_id
        """
        cur.execute(sql_children, (parent_ids,))
        for row in cur.fetchall():
            ref_id = row[0]
            children_map.setdefault(ref_id, []).append(row)

    conn.close()

    return templates.TemplateResponse(
        "ips.html",
        {
            "request": request,
            "rows": parent_rows,     # list of tuples (see SELECT order above)
            "children": children_map,  # dict: parent_id -> list of child tuples
            "q": q or "",
            "page": page,
            "per_page": per_page,
            "total": total,
        },
    )
