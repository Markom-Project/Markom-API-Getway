"""Cost tab — spend by model, team, key, trends, CSV export."""

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

logger = logging.getLogger("markom_gateway.routes.cost")
router = APIRouter(prefix="/api/cost", tags=["cost"])

LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")


def _extract_api_key(authorization: Optional[str] = None) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return authorization


def _require_tab(authorization: Optional[str], tab: str = "cost"):
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


@router.get("/summary")
async def cost_summary(
    days: int = Query(30, ge=1, le=365),
    authorization: Optional[str] = Header(None),
):
    _require_tab(authorization)
    start, end = _date_range(days)
    try:
        data = await _litellm_get("/global/spend", {"start_date": start, "end_date": end})
        results = data.get("results", [])
        total = sum(float(r.get("total_cost", 0)) for r in results)
        by_date = {}
        for r in results:
            d = r.get("date", "unknown")
            by_date[d] = by_date.get(d, 0) + float(r.get("total_cost", 0))
        return {
            "total_spend": round(total, 4),
            "by_date": {k: round(v, 4) for k, v in sorted(by_date.items())},
            "period_days": days,
        }
    except Exception as e:
        logger.error("Cost summary failed: %s", e)
        return {"total_spend": 0, "by_date": {}, "period_days": days}


@router.get("/by-model")
async def cost_by_model(
    days: int = Query(30, ge=1, le=365),
    authorization: Optional[str] = Header(None),
):
    _require_tab(authorization)
    start, end = _date_range(days)
    try:
        data = await _litellm_get("/global/spend/models", {"start_date": start, "end_date": end})
        return data
    except Exception as e:
        logger.error("Cost by model failed: %s", e)
        return {"models": []}


@router.get("/by-team")
async def cost_by_team(
    days: int = Query(30, ge=1, le=365),
    authorization: Optional[str] = Header(None),
):
    _require_tab(authorization)
    start, end = _date_range(days)
    try:
        data = await _litellm_get("/global/spend/teams", {"start_date": start, "end_date": end})
        return data
    except Exception as e:
        logger.error("Cost by team failed: %s", e)
        return {"teams": []}


@router.get("/by-key")
async def cost_by_key(
    days: int = Query(30, ge=1, le=365),
    authorization: Optional[str] = Header(None),
):
    _require_tab(authorization)
    start, end = _date_range(days)
    try:
        data = await _litellm_get("/global/spend/keys", {"start_date": start, "end_date": end})
        return data
    except Exception as e:
        logger.error("Cost by key failed: %s", e)
        return {"keys": []}


@router.get("/trend")
async def cost_trend(
    days: int = Query(30, ge=1, le=365),
    authorization: Optional[str] = Header(None),
):
    _require_tab(authorization)
    start, end = _date_range(days)
    try:
        data = await _litellm_get("/global/spend/logs", {"start_date": start, "end_date": end})
        return data
    except Exception as e:
        logger.error("Cost trend failed: %s", e)
        return {"logs": []}


@router.get("/export")
async def cost_export(
    days: int = Query(30, ge=1, le=365),
    authorization: Optional[str] = Header(None),
):
    user = _require_tab(authorization)
    if not RBACService.has_permission(user["external_id"], "export_audit"):
        raise HTTPException(status_code=403, detail="Permission denied: export_audit")
    start, end = _date_range(days)
    try:
        data = await _litellm_get("/global/spend/logs", {"start_date": start, "end_date": end})
        logs = data.get("logs", [])
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["date", "model", "team", "key", "cost", "tokens"])
        for row in logs:
            writer.writerow([
                row.get("date", ""),
                row.get("model", ""),
                row.get("team", ""),
                row.get("api_key", ""),
                row.get("total_cost", 0),
                row.get("total_tokens", 0),
            ])
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=markom-cost-{start}-to-{end}.csv"},
        )
    except Exception as e:
        logger.error("Cost export failed: %s", e)
        raise HTTPException(status_code=500, detail="Export failed")
