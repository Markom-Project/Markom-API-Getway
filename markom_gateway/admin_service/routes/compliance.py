"""Compliance tab — data principal export/delete (DPDPA right to erasure)."""

import logging
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..rbac import RBACService
from ..tab_matrix import has_tab_access

logger = logging.getLogger("markom_gateway.routes.compliance")
router = APIRouter(prefix="/api/compliance", tags=["compliance"])


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
    if not RBACService.has_permission(user["external_id"], "view_audit"):
        raise HTTPException(status_code=403, detail="Permission denied: view_audit")
    return user


class PrincipalExportRequest(BaseModel):
    data_principal_id: str


class PrincipalDeleteRequest(BaseModel):
    data_principal_id: str


@router.post("/principal/export")
async def export_principal(
    body: PrincipalExportRequest,
    authorization: Optional[str] = Header(None),
):
    """Export all audit records for a data principal (DPDPA right to access)."""
    user = _require_tab(authorization)
    from markom_gateway.hooks.audit_logger import MarkomAuditLogger

    result = MarkomAuditLogger.export_principal_data(body.data_principal_id)
    return result


@router.post("/principal/delete")
async def delete_principal(
    body: PrincipalDeleteRequest,
    authorization: Optional[str] = Header(None),
):
    """Delete prompt/response content for a data principal (DPDPA right to erasure).
    Audit metadata is preserved for compliance history."""
    user = _require_tab(authorization)
    if not RBACService.has_permission(user["external_id"], "export_audit"):
        raise HTTPException(status_code=403, detail="Permission denied: export_audit")
    from markom_gateway.hooks.audit_logger import MarkomAuditLogger

    result = MarkomAuditLogger.delete_principal_data(body.data_principal_id)
    return result


@router.post("/retention/purge")
async def purge_expired(
    authorization: Optional[str] = Header(None),
):
    """Run retention purge for all data types using configured windows."""
    user = _require_tab(authorization)
    if not RBACService.has_permission(user["external_id"], "export_audit"):
        raise HTTPException(status_code=403, detail="Permission denied: export_audit")

    import os
    from markom_gateway.hooks.audit_logger import MarkomAuditLogger

    audit_days = int(os.environ.get("MARKOM_AUDIT_RETENTION_DAYS", "90"))
    prompt_days = int(os.environ.get("MARKOM_PROMPT_RETENTION_DAYS", "30"))

    audit_deleted = MarkomAuditLogger.purge_old_records(audit_days)
    prompt_redacted = MarkomAuditLogger.purge_old_prompt_content(prompt_days)

    return {
        "audit_records_deleted": audit_deleted,
        "prompt_records_redacted": prompt_redacted,
        "audit_retention_days": audit_days,
        "prompt_retention_days": prompt_days,
    }


@router.get("/retention/config")
async def retention_config(
    authorization: Optional[str] = Header(None),
):
    """Return current retention configuration."""
    _require_tab(authorization)
    import os
    return {
        "audit_retention_days": int(os.environ.get("MARKOM_AUDIT_RETENTION_DAYS", "90")),
        "prompt_retention_days": int(os.environ.get("MARKOM_PROMPT_RETENTION_DAYS", "30")),
        "cache_retention_days": int(os.environ.get("MARKOM_CACHE_RETENTION_DAYS", "30")),
        "redact_content": os.environ.get("MARKOM_AUDIT_REDACT_CONTENT", "false").lower() == "true",
        "raw_content_teams": os.environ.get("MARKOM_AUDIT_RAW_CONTENT_TEAMS", ""),
    }
