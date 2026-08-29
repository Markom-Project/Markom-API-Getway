"""Guardrails tab — trigger log, audit trail viewer, export."""

import csv
import io
import logging
import os
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import Optional

from ..rbac import RBACService
from ..tab_matrix import has_tab_access

logger = logging.getLogger("markom_gateway.routes.guardrails")
router = APIRouter(prefix="/api/guardrails", tags=["guardrails"])

_db_pool = None


def _get_audit_pool():
    global _db_pool
    if _db_pool is not None:
        return _db_pool
    dsn = os.environ.get("MARKOM_ADMIN_DB_URL") or os.environ.get("DATABASE_URL")
    if not dsn:
        return None
    try:
        import psycopg_pool
        _db_pool = psycopg_pool.ConnectionPool(dsn, min_size=1, max_size=3)
        return _db_pool
    except Exception:
        return None


def _extract_api_key(authorization: Optional[str] = None) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return authorization


def _require_tab(authorization: Optional[str], tab: str = "guardrails"):
    api_key = _extract_api_key(authorization)
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing authorization")
    user = RBACService.get_user_by_api_key(api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if not has_tab_access(user["external_id"], tab):
        raise HTTPException(status_code=403, detail=f"Access denied: {tab}")
    return user


def _date_range(days: int = 7) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    return start.isoformat(), now.isoformat()


@router.get("/triggers")
async def guardrail_triggers(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(100, ge=1, le=1000),
    authorization: Optional[str] = Header(None),
):
    _require_tab(authorization)
    pool = _get_audit_pool()
    if pool is None:
        return {"triggers": [], "total": 0}
    start, end = _date_range(days)
    try:
        with pool.connection() as conn:
            cursor = conn.execute(
                """
                SELECT timestamp, user_id, model, guardrail_results
                FROM markom_audit_log
                WHERE timestamp BETWEEN %s AND %s
                  AND guardrail_results IS NOT NULL
                  AND guardrail_results != '{}'
                ORDER BY timestamp DESC
                LIMIT %s
                """,
                (start, end, limit),
            )
            rows = cursor.fetchall()
            triggers = []
            for row in rows:
                triggers.append({
                    "timestamp": str(row[0]),
                    "user_id": row[1],
                    "model": row[2],
                    "guardrail_results": row[3],
                })
            return {"triggers": triggers, "total": len(triggers)}
    except Exception as e:
        logger.error("Guardrail triggers query failed: %s", e)
        return {"triggers": [], "total": 0}


@router.get("/audit")
async def guardrail_audit(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
):
    _require_tab(authorization)
    pool = _get_audit_pool()
    if pool is None:
        return {"records": [], "total": 0}
    start, end = _date_range(days)
    try:
        with pool.connection() as conn:
            query = """
                SELECT id, timestamp, request_id, user_id, team_id,
                       model, provider, prompt_tokens, completion_tokens,
                       total_tokens, cost_usd, latency_ms, status, error_message,
                       guardrail_results, routing_decision, metadata
                FROM markom_audit_log
                WHERE timestamp BETWEEN %s AND %s
            """
            params = [start, end]
            if status:
                query += " AND status = %s"
                params.append(status)
            query += " ORDER BY timestamp DESC LIMIT %s"
            params.append(limit)
            cursor = conn.execute(query, params)
            columns = [desc[0] for desc in cursor.description]
            records = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return {"records": records, "total": len(records)}
    except Exception as e:
        logger.error("Guardrail audit query failed: %s", e)
        return {"records": [], "total": 0}


@router.get("/audit/export")
async def guardrail_audit_export(
    days: int = Query(30, ge=1, le=365),
    authorization: Optional[str] = Header(None),
):
    user = _require_tab(authorization)
    if not RBACService.has_permission(user["external_id"], "export_audit"):
        raise HTTPException(status_code=403, detail="Permission denied: export_audit")
    pool = _get_audit_pool()
    if pool is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    start, end = _date_range(days)
    try:
        with pool.connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, timestamp, request_id, user_id, team_id,
                       model, provider, prompt_tokens, completion_tokens,
                       total_tokens, cost_usd, latency_ms, status, error_message
                FROM markom_audit_log
                WHERE timestamp BETWEEN %s AND %s
                ORDER BY timestamp DESC
                """,
                (start, end),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(columns)
            for row in rows:
                writer.writerow(row)
            output.seek(0)
            return StreamingResponse(
                iter([output.getvalue()]),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=markom-audit-{start[:10]}-to-{end[:10]}.csv"},
            )
    except Exception as e:
        logger.error("Audit export failed: %s", e)
        raise HTTPException(status_code=500, detail="Export failed")
