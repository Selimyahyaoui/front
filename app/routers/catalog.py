# app/routers/catalog.py
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from app.db.database import get_connection

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _rows_count(q: Optional[str]) -> int:
    """Count rows with optional search."""
    sql = """
        SELECT COUNT(*)
        FROM supchain.t_catalog_server c
        {where}
    """
    where = ""
    params: List[Any] = []
    if q:
        where = """
            WHERE
                LOWER(c.t_catalog_server_model)      LIKE %s OR
                LOWER(c.t_catalog_server_vendor)     LIKE %s OR
                LOWER(COALESCE(c.t_catalog_server_comments, '')) LIKE %s
        """
        like = f"%{q.lower()}%"
        params = [like, like, like]

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql.format(where=where), params)
            (count,) = cur.fetchone()
            return int(count)


def _fetch_page(offset: int, limit: int, q: Optional[str]) -> List[Dict[str, Any]]:
    """Fetch a page of catalog rows with optional search."""
    base_sql = """
        SELECT
            c.t_catalog_server_id,
            c.t_catalog_server_model,
            c.t_catalog_server_vendor,
            c.t_catalog_server_reftech_id,
            c.t_catalog_server_refprod_id,
            c.t_catalog_server_comments,
            c.t_catalog_server_datetime_added,
            c.t_catalog_server_qualified,
            c.t_catalog_server_qualif_in_progress,
            c.t_catalog_server_availability
        FROM supchain.t_catalog_server c
        {where}
        ORDER BY c.t_catalog_server_id DESC
        LIMIT %s OFFSET %s
    """
    where = ""
    params: List[Any] = []
    if q:
        where = """
            WHERE
                LOWER(c.t_catalog_server_model)      LIKE %s OR
                LOWER(c.t_catalog_server_vendor)     LIKE %s OR
                LOWER(COALESCE(c.t_catalog_server_comments, '')) LIKE %s
        """
        like = f"%{q.lower()}%"
        params = [like, like, like]

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(base_sql.format(where=where), params + [limit, offset])
            rows = cur.fetchall()

    cols = [
        "t_catalog_server_id",
        "t_catalog_server_model",
        "t_catalog_server_vendor",
        "t_catalog_server_reftech_id",
        "t_catalog_server_refprod_id",
        "t_catalog_server_comments",
        "t_catalog_server_datetime_added",
        "t_catalog_server_qualified",
        "t_catalog_server_qualif_in_progress",
        "t_catalog_server_availability",
    ]
    return [dict(zip(cols, r)) for r in rows]


@router.get("/catalog", response_class=HTMLResponse)
async def page_catalog(
    request: Request,
    q: Optional[str] = Query(None, description="Search model/vendor/comments"),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=5, le=100),
):
    """
    List catalog servers with pagination and a very small search.
    """
    total = _rows_count(q)
    offset = (page - 1) * per_page
    rows = _fetch_page(offset, per_page, q)

    return templates.TemplateResponse(
        "catalog.html",
        {
            "request": request,
            "rows": rows,
            "page": page,
            "per_page": per_page,
            "total": total,
            "q": q or "",
        },
    )
