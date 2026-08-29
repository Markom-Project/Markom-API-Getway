"""
MarKom RBAC — Role-Based Access Control for the admin service.

Roles: admin, team_lead, developer, viewer
Persisted in Postgres table markom_roles.
"""

import hashlib
import logging
import os
import time
from enum import Enum
from typing import Optional

logger = logging.getLogger("markom_gateway.rbac")

_db_pool = None

ROLE_PERMISSIONS = {
    "admin": {
        "create_key",
        "delete_key",
        "view_key",
        "update_key",
        "create_team",
        "delete_team",
        "view_team",
        "update_team",
        "view_logs",
        "export_audit",
        "view_audit",
        "manage_users",
        "manage_roles",
        "view_budgets",
        "update_budgets",
    },
    "team_lead": {
        "view_key",
        "create_key",
        "update_key",
        "view_team",
        "update_team",
        "view_logs",
        "view_audit",
        "view_budgets",
        "update_budgets",
    },
    "developer": {
        "view_key",
        "view_team",
        "view_logs",
    },
    "viewer": {
        "view_team",
        "view_logs",
    },
}


class Role(str, Enum):
    ADMIN = "admin"
    TEAM_LEAD = "team_lead"
    DEVELOPER = "developer"
    VIEWER = "viewer"


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

                CREATE INDEX IF NOT EXISTS idx_roles_user ON markom_roles (user_id);
                CREATE INDEX IF NOT EXISTS idx_roles_team ON markom_roles (team_id);
                CREATE INDEX IF NOT EXISTS idx_users_external ON markom_users (external_id);
                CREATE INDEX IF NOT EXISTS idx_users_api_key ON markom_users (api_key_hash);
                """
            )
            conn.commit()
    except Exception as e:
        logger.error("Failed to create RBAC tables: %s", e)


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
    def has_permission(user_external_id: str, permission: str, team_id: str = None) -> bool:
        role = RBACService.get_user_role(user_external_id, team_id)
        return permission in ROLE_PERMISSIONS.get(role, set())

    @staticmethod
    def get_user_by_api_key(api_key: str) -> Optional[dict]:
        """Look up a user by their API key hash. Returns dict with external_id and role."""
        if not api_key:
            return None
        pool = _get_db_pool()
        if pool is None:
            return None
        try:
            api_key_hash = _hash_api_key(api_key)
            with pool.connection() as conn:
                cursor = conn.execute(
                    "SELECT external_id, role, email, display_name FROM markom_users WHERE api_key_hash = %s",
                    (api_key_hash,),
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "external_id": row[0],
                        "role": row[1],
                        "email": row[2],
                        "display_name": row[3],
                    }
        except Exception as e:
            logger.error("Failed to look up user by API key: %s", e)
        return None

    @staticmethod
    def set_user_role(
        user_external_id: str,
        role: str,
        email: str = None,
        display_name: str = None,
        team_id: str = None,
        granted_by: str = None,
        api_key: str = None,
    ) -> bool:
        if role not in ROLE_PERMISSIONS:
            raise ValueError(f"Invalid role: {role}. Must be one of: {list(ROLE_PERMISSIONS.keys())}")
        pool = _get_db_pool()
        if pool is None:
            logger.warning("Cannot set role: no database connection")
            return False
        try:
            api_key_hash = _hash_api_key(api_key) if api_key else None
            with pool.connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO markom_users (external_id, email, display_name, role, api_key_hash)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (external_id) DO UPDATE SET
                        email = COALESCE(EXCLUDED.email, markom_users.email),
                        display_name = COALESCE(EXCLUDED.display_name, markom_users.display_name),
                        role = EXCLUDED.role,
                        api_key_hash = COALESCE(EXCLUDED.api_key_hash, markom_users.api_key_hash),
                        updated_at = NOW()
                    RETURNING id
                    """,
                    (user_external_id, email, display_name, role, api_key_hash),
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
    def list_users(team_id: str = None) -> list[dict]:
        pool = _get_db_pool()
        if pool is None:
            return []
        try:
            with pool.connection() as conn:
                if team_id:
                    cursor = conn.execute(
                        """
                        SELECT u.external_id, u.email, u.display_name, r.role, r.granted_at
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
                        SELECT external_id, email, display_name, role, created_at
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
