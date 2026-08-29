"""Accounts tab — admin user CRUD (create/edit/disable/remove)."""

import logging
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional

from ..rbac import RBACService, _get_db_pool
from ..tab_matrix import has_tab_access

logger = logging.getLogger("markom_gateway.routes.accounts")
router = APIRouter(prefix="/api/accounts", tags=["accounts"])


class AccountCreate(BaseModel):
    external_id: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    role: str = "viewer"
    team_id: Optional[str] = None
    api_key: Optional[str] = None
    tab_overrides: Optional[list[str]] = []


class AccountUpdate(BaseModel):
    email: Optional[str] = None
    display_name: Optional[str] = None
    role: Optional[str] = None
    tab_overrides: Optional[list[str]] = None
    api_key: Optional[str] = None


def _extract_api_key(authorization: Optional[str] = None) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return authorization


def _require_admin(authorization: Optional[str]):
    api_key = _extract_api_key(authorization)
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing authorization")
    user = RBACService.get_user_by_api_key(api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if not has_tab_access(user["external_id"], "accounts"):
        raise HTTPException(status_code=403, detail="Access denied: accounts")
    if not RBACService.has_permission(user["external_id"], "manage_users"):
        raise HTTPException(status_code=403, detail="Permission denied: manage_users")
    return user


@router.get("")
async def list_accounts(authorization: Optional[str] = Header(None)):
    _require_admin(authorization)
    users = RBACService.list_users()
    result = []
    for u in users:
        tabs = RBACService.get_user_tabs(u["external_id"])
        result.append({
            "external_id": u["external_id"],
            "email": u.get("email"),
            "display_name": u.get("display_name"),
            "role": u.get("role", "viewer"),
            "tabs": tabs,
            "tab_overrides": u.get("tab_overrides", []),
            "created_at": str(u.get("created_at", "")),
        })
    return {"accounts": result}


@router.post("")
async def create_account(body: AccountCreate, authorization: Optional[str] = Header(None)):
    _require_admin(authorization)
    try:
        success = RBACService.set_user_role(
            user_external_id=body.external_id,
            role=body.role,
            email=body.email,
            display_name=body.display_name,
            team_id=body.team_id,
            api_key=body.api_key,
            tab_overrides=body.tab_overrides,
        )
        if not success:
            raise HTTPException(status_code=500, detail="Failed to create account")
        return {"status": "created", "external_id": body.external_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{external_id}")
async def update_account(
    external_id: str,
    body: AccountUpdate,
    authorization: Optional[str] = Header(None),
):
    _require_admin(authorization)
    fields = {}
    if body.email is not None:
        fields["email"] = body.email
    if body.display_name is not None:
        fields["display_name"] = body.display_name
    if body.role is not None:
        fields["role"] = body.role
    if body.tab_overrides is not None:
        fields["tab_overrides"] = body.tab_overrides
    if body.api_key is not None:
        fields["api_key"] = body.api_key
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    success = RBACService.update_user(external_id, **fields)
    if not success:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"status": "updated", "external_id": external_id}


@router.post("/{external_id}/disable")
async def disable_account(external_id: str, authorization: Optional[str] = Header(None)):
    _require_admin(authorization)
    success = RBACService.update_user(external_id, role="disabled")
    if not success:
        raise HTTPException(status_code=404, detail="Account not found")
    pool = _get_db_pool()
    if pool:
        try:
            with pool.connection() as conn:
                conn.execute(
                    "INSERT INTO markom_audit_log (timestamp, user_id, metadata) VALUES (NOW(), %s, %s)",
                    (external_id, '{"action": "account_disabled"}'),
                )
                conn.commit()
        except Exception:
            pass
    return {"status": "disabled", "external_id": external_id}


@router.post("/{external_id}/remove")
async def remove_account(external_id: str, authorization: Optional[str] = Header(None)):
    _require_admin(authorization)
    pool = _get_db_pool()
    if pool:
        try:
            with pool.connection() as conn:
                conn.execute(
                    "INSERT INTO markom_audit_log (timestamp, user_id, metadata) VALUES (NOW(), %s, %s)",
                    (external_id, '{"action": "account_removed"}'),
                )
                conn.commit()
        except Exception:
            pass
    success = RBACService.remove_user(external_id)
    if not success:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"status": "removed", "external_id": external_id}
