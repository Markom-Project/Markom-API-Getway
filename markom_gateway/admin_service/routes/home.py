"""Home tab — summary cards, health status, activity chart."""

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Header, HTTPException
from typing import Optional

from ..rbac import RBACService
from ..tab_matrix import has_tab_access

logger = logging.getLogger("markom_gateway.routes.home")
router = APIRouter(prefix="/api/home", tags=["home"])

LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")


def _extract_api_key(authorization: Optional[str] = None) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return authorization


def _require_tab(authorization: Optional[str], tab: str):
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


@router.get("/summary")
async def home_summary(authorization: Optional[str] = Header(None)):
    _require_tab(authorization, "home")

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    seven_days_ago = now - timedelta(days=7)

    try:
        spend_data = await _litellm_get(
            "/global/spend",
            {"start_date": seven_days_ago.strftime("%Y-%m-%d"), "end_date": now.strftime("%Y-%m-%d")},
        )
        total_spend = sum(float(s.get("total_cost", 0)) for s in spend_data.get("results", []))
        today_spend = 0.0
        for s in spend_data.get("results", []):
            if s.get("date") == now.strftime("%Y-%m-%d"):
                today_spend = float(s.get("total_cost", 0))
    except Exception:
        total_spend = 0.0
        today_spend = 0.0

    try:
        activity = await _litellm_get(
            "/global/activity",
            {"start_date": seven_days_ago.strftime("%Y-%m-%d"), "end_date": now.strftime("%Y-%m-%d")},
        )
        total_requests = sum(a.get("total_requests", 0) for a in activity.get("results", []))
    except Exception:
        total_requests = 0

    try:
        health = await _litellm_get("/health")
        providers_up = sum(1 for h in health.get("healthy_endpoints", []) if h)
    except Exception:
        providers_up = 0

    cache_hit_rate = 0.0
    try:
        cache_data = await _litellm_get("/global/activity/cache_hits")
        cache_hit_rate = float(cache_data.get("hit_rate", 0))
    except Exception:
        pass

    return {
        "total_spend_7d": round(total_spend, 4),
        "today_spend": round(today_spend, 4),
        "total_requests_7d": total_requests,
        "providers_up": providers_up,
        "cache_hit_rate": round(cache_hit_rate, 4),
    }
