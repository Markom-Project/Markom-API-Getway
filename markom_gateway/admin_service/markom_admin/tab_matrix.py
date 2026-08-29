"""
MarKom Tab Matrix — single source of truth for tab and permission resolution.

Resolves a user's visible tabs and permissions by:
1. Looking up their role template from DB
2. Merging in any per-user tab overrides
3. Providing the final access set
"""

import logging
from typing import Optional

from .rbac import RBACService, ALL_TABS, ALL_PERMISSIONS

logger = logging.getLogger("markom_gateway.tab_matrix")

TAB_META = {
    "home": {"label": "Home", "icon": "home", "order": 0},
    "cost": {"label": "Cost", "icon": "dollar", "order": 1},
    "usage": {"label": "Usage", "icon": "chart", "order": 2},
    "providers": {"label": "Providers", "icon": "server", "order": 3},
    "guardrails": {"label": "Guardrails", "icon": "shield", "order": 4},
    "accounts": {"label": "Accounts", "icon": "users", "order": 5},
    "settings": {"label": "Settings", "icon": "cog", "order": 6},
}


def get_user_access(user_external_id: str) -> dict:
    """
    Return the full access profile for a user.

    Returns:
        {
            "user_id": str,
            "role": str,
            "tabs": [{"slug": str, "label": str, "icon": str, "order": int}],
            "permissions": [str],
            "is_admin": bool,
        }
    """
    user = RBACService.get_user(user_external_id)
    if not user:
        return _empty_access(user_external_id)

    role_slug = user["role"]
    user_overrides = user.get("tab_overrides", []) or []

    role_tabs = RBACService.get_role_tabs(role_slug)
    merged_tabs = list(dict.fromkeys(role_tabs + user_overrides))

    permissions = RBACService.get_role_permissions(role_slug)

    tab_list = [
        {
            "slug": slug,
            "label": TAB_META.get(slug, {}).get("label", slug.title()),
            "icon": TAB_META.get(slug, {}).get("icon", "circle"),
            "order": TAB_META.get(slug, {}).get("order", 99),
        }
        for slug in merged_tabs
        if slug in TAB_META
    ]
    tab_list.sort(key=lambda t: t["order"])

    return {
        "user_id": user_external_id,
        "role": role_slug,
        "tabs": tab_list,
        "permissions": sorted(permissions),
        "is_admin": role_slug == "admin",
    }


def has_tab_access(user_external_id: str, tab_slug: str) -> bool:
    """Check if user can access a specific tab."""
    user = RBACService.get_user(user_external_id)
    if not user:
        return False
    role_tabs = RBACService.get_role_tabs(user["role"])
    user_overrides = user.get("tab_overrides", []) or []
    return tab_slug in (role_tabs + user_overrides)


def has_permission(user_external_id: str, permission: str) -> bool:
    """Check if user has a specific permission."""
    user = RBACService.get_user(user_external_id)
    if not user:
        return False
    perms = RBACService.get_role_permissions(user["role"])
    return permission in perms


def _empty_access(user_external_id: str) -> dict:
    return {
        "user_id": user_external_id,
        "role": "viewer",
        "tabs": [{"slug": "home", "label": "Home", "icon": "home", "order": 0}],
        "permissions": [],
        "is_admin": False,
    }
