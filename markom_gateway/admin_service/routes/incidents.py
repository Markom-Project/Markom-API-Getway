"""Incidents tab — anomalous access patterns, repeated guardrail violations."""

import logging
import os
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Header, HTTPException, Query
from typing import Optional

from ..rbac import RBACService
from ..tab_matrix import has_tab_access

logger = logging.getLogger("markom_gateway.routes.incidents")
router = APIRouter(prefix="/api/incidents", tags=["incidents"])

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


@router.get("/anomalous-access")
async def anomalous_access(
    days: int = Query(7, ge=1, le=90),
    threshold: int = Query(50, ge=5, le=500),
    authorization: Optional[str] = Header(None),
):
    """Detect users with anomalous access patterns (high request volume, unusual hours)."""
    _require_tab(authorization)
    pool = _get_audit_pool()
    if pool is None:
        return {"incidents": [], "total": 0}

    start = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        with pool.connection() as conn:
            # Users with >threshold requests in the period
            cursor = conn.execute(
                """
                SELECT user_id, COUNT(*) as request_count,
                       COUNT(*) FILTER (WHERE status = 'failure') as failure_count,
                       SUM(cost_usd) as total_cost,
                       MIN(timestamp) as first_seen, MAX(timestamp) as last_seen
                FROM markom_audit_log
                WHERE timestamp >= %s AND user_id IS NOT NULL AND user_id != ''
                GROUP BY user_id
                HAVING COUNT(*) > %s
                ORDER BY request_count DESC
                """,
                (start, threshold),
            )
            rows = cursor.fetchall()
            incidents = []
            for row in rows:
                incidents.append({
                    "type": "high_volume",
                    "user_id": row[0],
                    "request_count": row[1],
                    "failure_count": row[2],
                    "total_cost": round(float(row[3] or 0), 4),
                    "first_seen": str(row[4]),
                    "last_seen": str(row[5]),
                    "severity": "high" if row[1] > threshold * 3 else "medium",
                })
            return {"incidents": incidents, "total": len(incidents)}
    except Exception as e:
        logger.error("Anomalous access query failed: %s", e)
        return {"incidents": [], "total": 0}


@router.get("/guardrail-violations")
async def guardrail_violations(
    days: int = Query(7, ge=1, le=90),
    min_violations: int = Query(3, ge=1, le=50),
    authorization: Optional[str] = Header(None),
):
    """Detect users with repeated guardrail violations."""
    _require_tab(authorization)
    pool = _get_audit_pool()
    if pool is None:
        return {"incidents": [], "total": 0}

    start = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        with pool.connection() as conn:
            cursor = conn.execute(
                """
                SELECT user_id, model,
                       COUNT(*) as violation_count,
                       MAX(timestamp) as last_violation,
                       ARRAY_AGG(DISTINCT guardrail_results->>'pii_detected') as pii_flags
                FROM markom_audit_log
                WHERE timestamp >= %s
                  AND guardrail_results IS NOT NULL
                  AND guardrail_results != '{}'
                  AND user_id IS NOT NULL AND user_id != ''
                GROUP BY user_id, model
                HAVING COUNT(*) >= %s
                ORDER BY violation_count DESC
                """,
                (start, min_violations),
            )
            rows = cursor.fetchall()
            incidents = []
            for row in rows:
                incidents.append({
                    "type": "repeated_guardrail_violation",
                    "user_id": row[0],
                    "model": row[1],
                    "violation_count": row[2],
                    "last_violation": str(row[3]),
                    "pii_flags": row[4] if row[4] else [],
                    "severity": "high" if row[2] >= min_violations * 3 else "medium",
                })
            return {"incidents": incidents, "total": len(incidents)}
    except Exception as e:
        logger.error("Guardrail violations query failed: %s", e)
        return {"incidents": [], "total": 0}


@router.get("/summary")
async def incident_summary(
    days: int = Query(7, ge=1, le=90),
    authorization: Optional[str] = Header(None),
):
    """Summary of all incident types for the providers/guardrails tab banner."""
    _require_tab(authorization)
    pool = _get_audit_pool()
    if pool is None:
        return {"total_incidents": 0, "by_type": {}}

    start = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        with pool.connection() as conn:
            # High-volume users
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT user_id FROM markom_audit_log
                    WHERE timestamp >= %s AND user_id IS NOT NULL AND user_id != ''
                    GROUP BY user_id HAVING COUNT(*) > 50
                ) sub
                """,
                (start,),
            )
            high_volume = cursor.fetchone()[0]

            # Guardrail violations
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT user_id FROM markom_audit_log
                    WHERE timestamp >= %s
                      AND guardrail_results IS NOT NULL
                      AND guardrail_results != '{}'
                      AND user_id IS NOT NULL AND user_id != ''
                    GROUP BY user_id HAVING COUNT(*) >= 3
                ) sub
                """,
                (start,),
            )
            guardrail_violators = cursor.fetchone()[0]

            # High error rate users
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT user_id,
                           COUNT(*) FILTER (WHERE status = 'failure')::float / NULLIF(COUNT(*), 0) as error_rate
                    FROM markom_audit_log
                    WHERE timestamp >= %s AND user_id IS NOT NULL AND user_id != ''
                    GROUP BY user_id
                    HAVING COUNT(*) > 10
                       AND COUNT(*) FILTER (WHERE status = 'failure')::float / NULLIF(COUNT(*), 0) > 0.3
                ) sub
                """,
                (start,),
            )
            high_error_users = cursor.fetchone()[0]

            total = high_volume + guardrail_violators + high_error_users
            return {
                "total_incidents": total,
                "by_type": {
                    "high_volume_access": high_volume,
                    "guardrail_violations": guardrail_violators,
                    "high_error_rate": high_error_users,
                },
                "period_days": days,
            }
    except Exception as e:
        logger.error("Incident summary query failed: %s", e)
        return {"total_incidents": 0, "by_type": {}}
