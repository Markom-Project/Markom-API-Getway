"""Auth route — GET /api/auth/me"""

import logging
from fastapi import APIRouter, Header, HTTPException
from typing import Optional

from ..rbac import RBACService, _get_db_pool
from ..tab_matrix import get_user_access

logger = logging.getLogger("markom_gateway.routes.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _extract_api_key(authorization: Optional[str] = None) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return authorization


@router.get("/me")
async def auth_me(authorization: Optional[str] = Header(None)):
    api_key = _extract_api_key(authorization)
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    user = RBACService.get_user_by_api_key(api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")

    access = get_user_access(user["external_id"])
    return {
        "user_id": user["external_id"],
        "email": user.get("email"),
        "display_name": user.get("display_name"),
        "role": access["role"],
        "tabs": access["tabs"],
        "permissions": access["permissions"],
        "is_admin": access["is_admin"],
    }
