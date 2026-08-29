"""
MarKom RBAC — Role-Based Access Control for the admin service.

DB-backed role templates, per-user tab overrides, and fine-grained permissions.
Tables: markom_users, markom_roles, markom_roles_config, markom_role_templates
"""

import hashlib
import json
import logging
import os
from typing import Optional

logger = logging.getLogger("markom_gateway.rbac")

_db_pool = None

DEFAULT_ROLES = [
    {
        "slug": "admin",
        "display_name": "Administrator",
        "description": "Full access to all features",
        "is_system": True,
        "tabs": ["home", "cost", "usage", "providers", "guardrails", "accounts", "settings"],
        "permissions": [
            "create_key", "delete_key", "view_key", "update_key",
            "create_team", "delete_team", "view_team", "update_team",
            "view_logs", "export_audit", "view_audit",
            "manage_users", "manage_roles", "view_budgets", "update_budgets",
        ],
    },
    {
        "slug": "team_lead",
        "display_name": "Team Lead",
        "description": "Team-level analytics and cost management",
        "is_system": False,
        "tabs": ["home", "cost", "usage"],
        "permissions": [
            "view_key", "create_key", "update_key",
            "view_team", "update_team",
            "view_logs", "view_audit",
            "view_budgets", "update_budgets",
        ],
    },
    {
        "slug": "developer",
        "display_name": "Developer",
        "description": "View-only access to home and usage",
        "is_system": False,
        "tabs": ["home", "usage"],
        "permissions": ["view_key", "view_team", "view_logs"],
    },
    {
        "slug": "viewer",
        "display_name": "Viewer",
        "description": "Minimal read-only access",
        "is_system": False,
        "tabs": ["home"],
        "permissions": ["view_team", "view_logs"],
    },
]

ALL_TABS = ["home", "cost", "usage", "providers", "guardrails", "accounts", "settings"]

ALL_PERMISSIONS = [
    "create_key", "delete_key", "view_key", "update_key",
    "create_team", "delete_team", "view_team", "update_team",
    "view_logs", "export_audit", "view_audit",
    "manage_users", "manage_roles", "view_budgets", "update_budgets",
]


def _get_db_pool():
    global _db_pool
    if _db_pool is not None:
        return _db_pool
    dsn = os.environ.get("MARKOM_ADMIN_DB_URL") or os.environ.get("DATABASE_URL")
    if not dsn:
        logger.warning("No database URL configured for RBAC")
        return None
    try:
        import psycopg_pool

        _db_pool = psycopg_pool.ConnectionPool(dsn, min_size=1, max_size=5)
        _ensure_rbac_tables(_db_pool)
        logger.info("RBAC connected to Postgres")
        return _db_pool
    except Exception as e:
        logger.warning("Failed to connect to Postgres for RBAC: %s", e)
        return None


def _ensure_rbac_tables(pool):
    try:
        with pool.connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS markom_users (
                    id BIGSERIAL PRIMARY KEY,
                    external_id TEXT UNIQUE NOT NULL,
                    email TEXT,
                    display_name TEXT,
                    role TEXT NOT NULL DEFAULT 'viewer',
                    api_key_hash TEXT,
                    tab_overrides JSONB DEFAULT '[]',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS markom_roles (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES markom_users(id),
                    team_id TEXT,
                    role TEXT NOT NULL,
                    granted_by TEXT,
                    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE(user_id, team_id)
                );

                CREATE TABLE IF NOT EXISTS markom_roles_config (
                    id BIGSERIAL PRIMARY KEY,
                    slug TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL,
                    description TEXT,
                    is_system BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS markom_role_templates (
                    id BIGSERIAL PRIMARY KEY,
                    role_slug TEXT UNIQUE NOT NULL REFERENCES markom_roles_config(slug) ON DELETE CASCADE,
                    tabs JSONB DEFAULT '[]',
                    permissions JSONB DEFAULT '[]',
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_by TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_roles_user ON markom_roles (user_id);
                CREATE INDEX IF NOT EXISTS idx_roles_team ON markom_roles (team_id);
                CREATE INDEX IF NOT EXISTS idx_users_external ON markom_users (external_id);
                CREATE INDEX IF NOT EXISTS idx_users_api_key ON markom_users (api_key_hash);
                CREATE INDEX IF NOT EXISTS idx_roles_config_slug ON markom_roles_config (slug);
                CREATE INDEX IF NOT EXISTS idx_role_templates_slug ON markom_role_templates (role_slug);
                """
            )
            conn.commit()
            _seed_default_roles(conn)
    except Exception as e:
        logger.error("Failed to create RBAC tables: %s", e)


def _seed_default_roles(conn):
    """Insert default role definitions and templates if none exist."""
    cursor = conn.execute("SELECT COUNT(*) FROM markom_roles_config")
    count = cursor.fetchone()[0]
    if count > 0:
        return
    for role in DEFAULT_ROLES:
        conn.execute(
            """
            INSERT INTO markom_roles_config (slug, display_name, description, is_system)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (slug) DO NOTHING
            """,
            (role["slug"], role["display_name"], role["description"], role["is_system"]),
        )
        conn.execute(
            """
            INSERT INTO markom_role_templates (role_slug, tabs, permissions)
            VALUES (%s, %s, %s)
            ON CONFLICT (role_slug) DO NOTHING
            """,
            (role["slug"], json.dumps(role["tabs"]), json.dumps(role["permissions"])),
        )
    conn.commit()
    logger.info("Seeded %d default roles", len(DEFAULT_ROLES))


def _hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()[:16]


class RBACService:
    @staticmethod
    def get_user_role(user_external_id: str, team_id: str = None) -> str:
        pool = _get_db_pool()
        if pool is None:
            return "viewer"
        try:
            with pool.connection() as conn:
                cursor = conn.execute(
                    "SELECT id FROM markom_users WHERE external_id = %s",
                    (user_external_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return "viewer"
                user_db_id = row[0]

                if team_id:
                    cursor = conn.execute(
                        "SELECT role FROM markom_roles WHERE user_id = %s AND team_id = %s",
                        (user_db_id, team_id),
                    )
                    role_row = cursor.fetchone()
                    if role_row:
                        return role_row[0]

                cursor = conn.execute(
                    "SELECT role FROM markom_users WHERE id = %s",
                    (user_db_id,),
                )
                role_row = cursor.fetchone()
                return role_row[0] if role_row else "viewer"
        except Exception as e:
            logger.error("Failed to get user role: %s", e)
            return "viewer"

    @staticmethod
    def get_user(user_external_id: str) -> Optional[dict]:
        """Return full user record including tab_overrides."""
        pool = _get_db_pool()
        if pool is None:
            return None
        try:
            with pool.connection() as conn:
                cursor = conn.execute(
                    """SELECT id, external_id, email, display_name, role,
                              api_key_hash, tab_overrides, created_at, updated_at
                       FROM markom_users WHERE external_id = %s""",
                    (user_external_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                return {
                    "id": row[0],
                    "external_id": row[1],
                    "email": row[2],
                    "display_name": row[3],
                    "role": row[4],
                    "api_key_hash": row[5],
                    "tab_overrides": row[6] if row[6] else [],
                    "created_at": str(row[7]),
                    "updated_at": str(row[8]),
                }
        except Exception as e:
            logger.error("Failed to get user: %s", e)
            return None

    @staticmethod
    def get_user_by_api_key(api_key: str) -> Optional[dict]:
        """Look up a user by their API key hash."""
        if not api_key:
            return None
        pool = _get_db_pool()
        if pool is None:
            return None
        try:
            api_key_hash = _hash_api_key(api_key)
            with pool.connection() as conn:
                cursor = conn.execute(
                    """SELECT external_id, role, email, display_name, tab_overrides
                       FROM markom_users WHERE api_key_hash = %s""",
                    (api_key_hash,),
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "external_id": row[0],
                        "role": row[1],
                        "email": row[2],
                        "display_name": row[3],
                        "tab_overrides": row[4] if row[4] else [],
                    }
        except Exception as e:
            logger.error("Failed to look up user by API key: %s", e)
        return None

    @staticmethod
    def has_permission(user_external_id: str, permission: str, team_id: str = None) -> bool:
        """Check if user has a specific permission via their role template."""
        role = RBACService.get_user_role(user_external_id, team_id)
        perms = RBACService.get_role_permissions(role)
        return permission in perms

    @staticmethod
    def get_role_permissions(role_slug: str) -> set[str]:
        """Return permissions for a role from DB templates."""
        pool = _get_db_pool()
        if pool is None:
            return set()
        try:
            with pool.connection() as conn:
                cursor = conn.execute(
                    "SELECT permissions FROM markom_role_templates WHERE role_slug = %s",
                    (role_slug,),
                )
                row = cursor.fetchone()
                return set(row[0]) if row else set()
        except Exception as e:
            logger.error("Failed to get role permissions: %s", e)
            return set()

    @staticmethod
    def get_user_tabs(user_external_id: str) -> list[str]:
        """Return merged tabs list: role_template.tabs + user.tab_overrides."""
        user = RBACService.get_user(user_external_id)
        if not user:
            return ["home"]
        role_slug = user["role"]
        role_tabs = RBACService.get_role_tabs(role_slug)
        user_overrides = user.get("tab_overrides", []) or []
        merged = list(dict.fromkeys(role_tabs + user_overrides))
        return merged

    @staticmethod
    def get_role_tabs(role_slug: str) -> list[str]:
        """Return tabs for a role from DB templates."""
        pool = _get_db_pool()
        if pool is None:
            return ["home"]
        try:
            with pool.connection() as conn:
                cursor = conn.execute(
                    "SELECT tabs FROM markom_role_templates WHERE role_slug = %s",
                    (role_slug,),
                )
                row = cursor.fetchone()
                return row[0] if row else ["home"]
        except Exception as e:
            logger.error("Failed to get role tabs: %s", e)
            return ["home"]

    @staticmethod
    def set_user_role(
        user_external_id: str,
        role: str,
        email: str = None,
        display_name: str = None,
        team_id: str = None,
        granted_by: str = None,
        api_key: str = None,
        tab_overrides: list[str] = None,
    ) -> bool:
        pool = _get_db_pool()
        if pool is None:
            logger.warning("Cannot set role: no database connection")
            return False
        try:
            api_key_hash = _hash_api_key(api_key) if api_key else None
            overrides_json = json.dumps(tab_overrides or [])
            with pool.connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO markom_users (external_id, email, display_name, role, api_key_hash, tab_overrides)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (external_id) DO UPDATE SET
                        email = COALESCE(EXCLUDED.email, markom_users.email),
                        display_name = COALESCE(EXCLUDED.display_name, markom_users.display_name),
                        role = EXCLUDED.role,
                        api_key_hash = COALESCE(EXCLUDED.api_key_hash, markom_users.api_key_hash),
                        tab_overrides = EXCLUDED.tab_overrides,
                        updated_at = NOW()
                    RETURNING id
                    """,
                    (user_external_id, email, display_name, role, api_key_hash, overrides_json),
                )
                user_db_id = cursor.fetchone()[0]

                if team_id:
                    conn.execute(
                        """
                        INSERT INTO markom_roles (user_id, team_id, role, granted_by)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (user_id, team_id) DO UPDATE SET
                            role = EXCLUDED.role,
                            granted_by = EXCLUDED.granted_by
                        """,
                        (user_db_id, team_id, role, granted_by),
                    )
                conn.commit()
                return True
        except Exception as e:
            logger.error("Failed to set user role: %s", e)
            return False

    @staticmethod
    def update_user(user_external_id: str, **fields) -> bool:
        """Update user fields: role, email, display_name, tab_overrides, status."""
        pool = _get_db_pool()
        if pool is None:
            return False
        try:
            sets = []
            vals = []
            if "role" in fields:
                sets.append("role = %s")
                vals.append(fields["role"])
            if "email" in fields:
                sets.append("email = %s")
                vals.append(fields["email"])
            if "display_name" in fields:
                sets.append("display_name = %s")
                vals.append(fields["display_name"])
            if "tab_overrides" in fields:
                sets.append("tab_overrides = %s")
                vals.append(json.dumps(fields["tab_overrides"]))
            if "api_key" in fields:
                sets.append("api_key_hash = %s")
                vals.append(_hash_api_key(fields["api_key"]))
            if not sets:
                return False
            sets.append("updated_at = NOW()")
            vals.append(user_external_id)
            with pool.connection() as conn:
                conn.execute(
                    f"UPDATE markom_users SET {', '.join(sets)} WHERE external_id = %s",
                    vals,
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error("Failed to update user: %s", e)
            return False

    @staticmethod
    def list_users(team_id: str = None) -> list[dict]:
        pool = _get_db_pool()
        if pool is None:
            return []
        try:
            with pool.connection() as conn:
                if team_id:
                    cursor = conn.execute(
                        """
                        SELECT u.external_id, u.email, u.display_name, r.role, r.granted_at,
                               u.tab_overrides
                        FROM markom_users u
                        JOIN markom_roles r ON u.id = r.user_id
                        WHERE r.team_id = %s
                        ORDER BY r.granted_at DESC
                        """,
                        (team_id,),
                    )
                else:
                    cursor = conn.execute(
                        """
                        SELECT external_id, email, display_name, role, created_at,
                               tab_overrides
                        FROM markom_users
                        ORDER BY created_at DESC
                        """
                    )
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            logger.error("Failed to list users: %s", e)
            return []

    @staticmethod
    def remove_user(user_external_id: str, team_id: str = None) -> bool:
        pool = _get_db_pool()
        if pool is None:
            return False
        try:
            with pool.connection() as conn:
                cursor = conn.execute(
                    "SELECT id FROM markom_users WHERE external_id = %s",
                    (user_external_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return False
                user_db_id = row[0]

                if team_id:
                    conn.execute(
                        "DELETE FROM markom_roles WHERE user_id = %s AND team_id = %s",
                        (user_db_id, team_id),
                    )
                else:
                    conn.execute("DELETE FROM markom_roles WHERE user_id = %s", (user_db_id,))
                    conn.execute("DELETE FROM markom_users WHERE id = %s", (user_db_id,))
                conn.commit()
                return True
        except Exception as e:
            logger.error("Failed to remove user: %s", e)
            return False

    # ── Role template CRUD ──────────────────────────────────────────────

    @staticmethod
    def list_roles() -> list[dict]:
        """List all role configs with their templates."""
        pool = _get_db_pool()
        if pool is None:
            return []
        try:
            with pool.connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT c.slug, c.display_name, c.description, c.is_system,
                           c.created_at, c.updated_at,
                           t.tabs, t.permissions, t.updated_by
                    FROM markom_roles_config c
                    LEFT JOIN markom_role_templates t ON c.slug = t.role_slug
                    ORDER BY c.is_system DESC, c.slug
                    """
                )
                roles = []
                for row in cursor.fetchall():
                    roles.append({
                        "slug": row[0],
                        "display_name": row[1],
                        "description": row[2],
                        "is_system": row[3],
                        "created_at": str(row[4]),
                        "updated_at": str(row[5]),
                        "tabs": row[6] or [],
                        "permissions": row[7] or [],
                        "updated_by": row[8],
                    })
                return roles
        except Exception as e:
            logger.error("Failed to list roles: %s", e)
            return []

    @staticmethod
    def get_role(slug: str) -> Optional[dict]:
        """Get single role config + template."""
        pool = _get_db_pool()
        if pool is None:
            return None
        try:
            with pool.connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT c.slug, c.display_name, c.description, c.is_system,
                           t.tabs, t.permissions, t.updated_by
                    FROM markom_roles_config c
                    LEFT JOIN markom_role_templates t ON c.slug = t.role_slug
                    WHERE c.slug = %s
                    """,
                    (slug,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                return {
                    "slug": row[0],
                    "display_name": row[1],
                    "description": row[2],
                    "is_system": row[3],
                    "tabs": row[4] or [],
                    "permissions": row[5] or [],
                    "updated_by": row[6],
                }
        except Exception as e:
            logger.error("Failed to get role: %s", e)
            return None

    @staticmethod
    def create_role(slug: str, display_name: str, description: str,
                    tabs: list[str] = None, permissions: list[str] = None,
                    created_by: str = None) -> bool:
        """Create a new custom role (non-system)."""
        pool = _get_db_pool()
        if pool is None:
            return False
        try:
            with pool.connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO markom_roles_config (slug, display_name, description, is_system)
                    VALUES (%s, %s, %s, FALSE)
                    RETURNING slug
                    """,
                    (slug, display_name, description),
                )
                cursor.fetchone()
                conn.execute(
                    """
                    INSERT INTO markom_role_templates (role_slug, tabs, permissions, updated_by)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (slug, json.dumps(tabs or []), json.dumps(permissions or []), created_by),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error("Failed to create role: %s", e)
            return False

    @staticmethod
    def update_role(slug: str, display_name: str = None, description: str = None,
                    tabs: list[str] = None, permissions: list[str] = None,
                    updated_by: str = None) -> bool:
        """Update role config and/or template."""
        pool = _get_db_pool()
        if pool is None:
            return False
        try:
            with pool.connection() as conn:
                if display_name is not None or description is not None:
                    sets = ["updated_at = NOW()"]
                    vals = []
                    if display_name is not None:
                        sets.append("display_name = %s")
                        vals.append(display_name)
                    if description is not None:
                        sets.append("description = %s")
                        vals.append(description)
                    vals.append(slug)
                    conn.execute(
                        f"UPDATE markom_roles_config SET {', '.join(sets)} WHERE slug = %s",
                        vals,
                    )
                if tabs is not None or permissions is not None:
                    t_sets = ["updated_at = NOW()"]
                    t_vals = []
                    if tabs is not None:
                        t_sets.append("tabs = %s")
                        t_vals.append(json.dumps(tabs))
                    if permissions is not None:
                        t_sets.append("permissions = %s")
                        t_vals.append(json.dumps(permissions))
                    if updated_by:
                        t_sets.append("updated_by = %s")
                        t_vals.append(updated_by)
                    t_vals.append(slug)
                    conn.execute(
                        f"UPDATE markom_role_templates SET {', '.join(t_sets)} WHERE role_slug = %s",
                        t_vals,
                    )
                conn.commit()
                return True
        except Exception as e:
            logger.error("Failed to update role: %s", e)
            return False

    @staticmethod
    def delete_role(slug: str) -> bool:
        """Delete a custom role (cannot delete system roles)."""
        pool = _get_db_pool()
        if pool is None:
            return False
        try:
            with pool.connection() as conn:
                cursor = conn.execute(
                    "SELECT is_system FROM markom_roles_config WHERE slug = %s",
                    (slug,),
                )
                row = cursor.fetchone()
                if not row:
                    return False
                if row[0]:
                    return False
                conn.execute(
                    "DELETE FROM markom_role_templates WHERE role_slug = %s",
                    (slug,),
                )
                conn.execute(
                    "DELETE FROM markom_roles_config WHERE slug = %s",
                    (slug,),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error("Failed to delete role: %s", e)
            return False
