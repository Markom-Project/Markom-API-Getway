"""Settings tab — role template management (list/create/edit/delete)."""

import logging
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..rbac import RBACService, ALL_TABS, ALL_PERMISSIONS
from ..tab_matrix import has_tab_access

logger = logging.getLogger("markom_gateway.routes.settings")
router = APIRouter(prefix="/api/settings", tags=["settings"])


class RoleCreate(BaseModel):
    slug: str
    display_name: str
    description: str = ""
    tabs: list[str] = []
    permissions: list[str] = []


class RoleUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    tabs: Optional[list[str]] = None
    permissions: Optional[list[str]] = None


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
    if not has_tab_access(user["external_id"], "settings"):
        raise HTTPException(status_code=403, detail="Access denied: settings")
    if not RBACService.has_permission(user["external_id"], "manage_roles"):
        raise HTTPException(status_code=403, detail="Permission denied: manage_roles")
    return user


@router.get("/roles")
async def list_roles(authorization: Optional[str] = Header(None)):
    _require_admin(authorization)
    roles = RBACService.list_roles()
    return {"roles": roles, "all_tabs": ALL_TABS, "all_permissions": ALL_PERMISSIONS}


@router.get("/roles/{slug}")
async def get_role(slug: str, authorization: Optional[str] = Header(None)):
    _require_admin(authorization)
    role = RBACService.get_role(slug)
    if not role:
        raise HTTPException(status_code=404, detail=f"Role not found: {slug}")
    return role


@router.post("/roles")
async def create_role(body: RoleCreate, authorization: Optional[str] = Header(None)):
    admin = _require_admin(authorization)
    if RBACService.get_role(body.slug):
        raise HTTPException(status_code=409, detail=f"Role already exists: {body.slug}")
    if body.slug not in ALL_TABS and not body.slug.replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid slug: use alphanumeric and underscores only")
    invalid_tabs = set(body.tabs) - set(ALL_TABS)
    if invalid_tabs:
        raise HTTPException(status_code=400, detail=f"Invalid tabs: {invalid_tabs}")
    invalid_perms = set(body.permissions) - set(ALL_PERMISSIONS)
    if invalid_perms:
        raise HTTPException(status_code=400, detail=f"Invalid permissions: {invalid_perms}")
    success = RBACService.create_role(
        slug=body.slug,
        display_name=body.display_name,
        description=body.description,
        tabs=body.tabs,
        permissions=body.permissions,
        created_by=admin["external_id"],
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to create role")
    return {"status": "created", "slug": body.slug}


@router.put("/roles/{slug}")
async def update_role(slug: str, body: RoleUpdate, authorization: Optional[str] = Header(None)):
    admin = _require_admin(authorization)
    existing = RBACService.get_role(slug)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Role not found: {slug}")
    if body.tabs is not None:
        invalid_tabs = set(body.tabs) - set(ALL_TABS)
        if invalid_tabs:
            raise HTTPException(status_code=400, detail=f"Invalid tabs: {invalid_tabs}")
    if body.permissions is not None:
        invalid_perms = set(body.permissions) - set(ALL_PERMISSIONS)
        if invalid_perms:
            raise HTTPException(status_code=400, detail=f"Invalid permissions: {invalid_perms}")
    success = RBACService.update_role(
        slug=slug,
        display_name=body.display_name,
        description=body.description,
        tabs=body.tabs,
        permissions=body.permissions,
        updated_by=admin["external_id"],
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update role")
    return {"status": "updated", "slug": slug}


@router.delete("/roles/{slug}")
async def delete_role(slug: str, authorization: Optional[str] = Header(None)):
    _require_admin(authorization)
    existing = RBACService.get_role(slug)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Role not found: {slug}")
    if existing.get("is_system"):
        raise HTTPException(status_code=403, detail="Cannot delete system role")
    success = RBACService.delete_role(slug)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete role")
    return {"status": "deleted", "slug": slug}
