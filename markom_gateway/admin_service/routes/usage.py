"""Usage tab — request volume, latency, error breakdown, cache hits."""

import logging
import os
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Header, HTTPException, Query
from typing import Optional

from ..rbac import RBACService
from ..tab_matrix import has_tab_access

logger = logging.getLogger("markom_gateway.routes.usage")
router = APIRouter(prefix="/api/usage", tags=["usage"])

LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")


def _extract_api_key(authorization: Optional[str] = None) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return authorization


def _require_tab(authorization: Optional[str], tab: str = "usage"):
    api_key = _extract_api_key(authorization)
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing authorization")
    user = RBACService.get_user_by_api_key(api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if not has_tab_access(user["external_id"], tab):
        raise HTTPException(status_code=403, detail=f"Access denied: {tab}")
    return user


async def _litellm_get(path: str, params: dict = None) -> dict:
    import httpx
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{LITELLM_URL}{path}", params=params or {})
        resp.raise_for_status()
        return resp.json()


def _date_range(days: int = 30) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    return start.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")


@router.get("/requests")
async def usage_requests(
    days: int = Query(30, ge=1, le=365),
    authorization: Optional[str] = Header(None),
):
    _require_tab(authorization)
    start, end = _date_range(days)
    try:
        data = await _litellm_get("/global/activity", {"start_date": start, "end_date": end})
        results = data.get("results", [])
        by_date = {}
        for r in results:
            d = r.get("date", "unknown")
            by_date[d] = by_date.get(d, 0) + r.get("total_requests", 0)
        return {"by_date": dict(sorted(by_date.items())), "period_days": days}
    except Exception as e:
        logger.error("Usage requests failed: %s", e)
        return {"by_date": {}, "period_days": days}


@router.get("/latency")
async def usage_latency(
    days: int = Query(7, ge=1, le=30),
    authorization: Optional[str] = Header(None),
):
    _require_tab(authorization)
    start, end = _date_range(days)
    try:
        data = await _litellm_get("/spend/logs/v2", {"start_date": start, "end_date": end})
        logs = data.get("logs", [])
        by_model = {}
        for log in logs:
            model = log.get("model", "unknown")
            latency = log.get("latency_ms", 0) or 0
            if model not in by_model:
                by_model[model] = {"latencies": [], "count": 0}
            by_model[model]["latencies"].append(latency)
            by_model[model]["count"] += 1
        result = {}
        for model, info in by_model.items():
            lats = sorted(info["latencies"])
            n = len(lats)
            result[model] = {
                "count": n,
                "p50": lats[n // 2] if n else 0,
                "p95": lats[int(n * 0.95)] if n else 0,
                "p99": lats[int(n * 0.99)] if n else 0,
                "avg": round(sum(lats) / n, 2) if n else 0,
            }
        return {"by_model": result, "period_days": days}
    except Exception as e:
        logger.error("Usage latency failed: %s", e)
        return {"by_model": {}, "period_days": days}


@router.get("/errors")
async def usage_errors(
    days: int = Query(7, ge=1, le=30),
    authorization: Optional[str] = Header(None),
):
    _require_tab(authorization)
    start, end = _date_range(days)
    try:
        data = await _litellm_get("/global/activity/exceptions", {"start_date": start, "end_date": end})
        results = data.get("results", [])
        by_date = {}
        for r in results:
            d = r.get("date", "unknown")
            by_date[d] = by_date.get(d, 0) + r.get("error_count", 0)
        return {"by_date": dict(sorted(by_date.items())), "period_days": days}
    except Exception as e:
        logger.error("Usage errors failed: %s", e)
        return {"by_date": {}, "period_days": days}


@router.get("/cache-hits")
async def usage_cache_hits(
    days: int = Query(7, ge=1, le=30),
    authorization: Optional[str] = Header(None),
):
    _require_tab(authorization)
    start, end = _date_range(days)
    try:
        data = await _litellm_get("/global/activity/cache_hits")
        return {
            "hit_rate": data.get("hit_rate", 0),
            "total_hits": data.get("total_hits", 0),
            "total_misses": data.get("total_misses", 0),
            "period_days": days,
        }
    except Exception as e:
        logger.error("Usage cache hits failed: %s", e)
        return {"hit_rate": 0, "total_hits": 0, "total_misses": 0, "period_days": days}
