"""Providers tab — health scores, routing log, toggle providers."""

import logging
import os
from fastapi import APIRouter, Header, HTTPException, Query
from typing import Optional

from ..rbac import RBACService
from ..tab_matrix import has_tab_access

logger = logging.getLogger("markom_gateway.routes.providers")
router = APIRouter(prefix="/api/providers", tags=["providers"])

LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")


def _extract_api_key(authorization: Optional[str] = None) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return authorization


def _require_tab(authorization: Optional[str], tab: str = "providers"):
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


async def _litellm_post(path: str, json_data: dict = None) -> dict:
    import httpx
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{LITELLM_URL}{path}", json=json_data or {})
        resp.raise_for_status()
        return resp.json()


@router.get("/health")
async def providers_health(authorization: Optional[str] = Header(None)):
    _require_tab(authorization)
    try:
        data = await _litellm_get("/health")
        healthy = data.get("healthy_endpoints", [])
        unhealthy = data.get("unhealthy_endpoints", [])
        results = []
        for ep in healthy:
            results.append({
                "model": ep.get("model", "unknown"),
                "provider": ep.get("api_base", "unknown"),
                "status": "healthy",
                "latency": ep.get("latency", 0),
            })
        for ep in unhealthy:
            results.append({
                "model": ep.get("model", "unknown"),
                "provider": ep.get("api_base", "unknown"),
                "status": "unhealthy",
                "latency": ep.get("latency", 0),
                "error": ep.get("error", "unknown"),
            })
        return {"providers": results}
    except Exception as e:
        logger.error("Provider health failed: %s", e)
        return {"providers": []}


@router.get("/routing-log")
async def providers_routing_log(
    limit: int = Query(50, ge=1, le=200),
    authorization: Optional[str] = Header(None),
):
    _require_tab(authorization)
    try:
        data = await _litellm_get("/global/activity/routing", {"limit": limit})
        return data
    except Exception as e:
        logger.error("Routing log failed: %s", e)
        return {"routing_decisions": []}


@router.post("/{model}/toggle")
async def providers_toggle(
    model: str,
    enable: bool = Query(True),
    authorization: Optional[str] = Header(None),
):
    user = _require_tab(authorization)
    if not RBACService.has_permission(user["external_id"], "manage_users"):
        raise HTTPException(status_code=403, detail="Permission denied: manage_users")
    try:
        if enable:
            result = await _litellm_post("/model/unblock", {"model_name": model})
        else:
            result = await _litellm_post("/model/block", {"model_name": model})
        return {"model": model, "enabled": enable, "result": result}
    except Exception as e:
        logger.error("Provider toggle failed: %s", e)
        raise HTTPException(status_code=500, detail="Toggle failed")
