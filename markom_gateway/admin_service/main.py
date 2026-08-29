"""
MarKom Admin Service — FastAPI app providing RBAC-gated management endpoints.

Proxies requests to LiteLLM's management API with RBAC enforcement.
"""

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from markom_gateway.admin_service.routes.auth import router as auth_router
from markom_gateway.admin_service.routes.home import router as home_router
from markom_gateway.admin_service.routes.cost import router as cost_router
from markom_gateway.admin_service.routes.usage import router as usage_router
from markom_gateway.admin_service.routes.providers import router as providers_router
from markom_gateway.admin_service.routes.guardrails import router as guardrails_router
from markom_gateway.admin_service.routes.accounts import router as accounts_router
from markom_gateway.admin_service.routes.settings import router as settings_router

logger = logging.getLogger("markom_gateway.admin_service")

app = FastAPI(
    title="MarKom Gateway Admin",
    description="RBAC-gated admin service for MarKom Gateway",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LITELLM_PROXY_URL = os.environ.get("LITELLM_PROXY_URL", "http://localhost:4000")
LITELLM_MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", os.environ.get("MARKOM_MASTER_KEY", ""))

UI_DIR = Path(__file__).parent / "markom_admin" / "ui"
if UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(UI_DIR / "static")), name="static")


# ── Models ──────────────────────────────────────────────────────────


class UserRole(BaseModel):
    user_id: str
    role: str
    team_id: Optional[str] = None
    email: Optional[str] = None
    display_name: Optional[str] = None
    api_key: Optional[str] = None


class AuditQuery(BaseModel):
    user_id: Optional[str] = None
    team_id: Optional[str] = None
    model: Optional[str] = None
    status: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    limit: int = 100
    offset: int = 0


class CachePurgeRequest(BaseModel):
    confirm: bool = False


# ── Dependencies ────────────────────────────────────────────────────


def _extract_user_from_header(x_user_id: str = Header(None)) -> Optional[str]:
    return x_user_id


def _require_auth(authorization: str = Header(None)) -> dict:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    token = authorization.replace("Bearer ", "")
    if token != LITELLM_MASTER_KEY:
        from markom_gateway.admin_service.markom_admin.rbac import RBACService
        user = RBACService.get_user_by_api_key(token)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return {"user_id": user["external_id"], "role": user.get("role", "viewer")}
    return {"user_id": "admin", "role": "admin"}


def _require_permission(permission: str, user_info: dict = Depends(_require_auth)):
    from markom_gateway.admin_service.markom_admin.rbac import RBACService
    if user_info["role"] != "admin" and not RBACService.has_permission(
        user_info["user_id"], permission
    ):
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied: {permission} requires role with {permission} access",
        )
    return user_info


async def _proxy_to_litellm(
    method: str,
    path: str,
    body: dict = None,
    user_info: dict = None,
) -> dict:
    import httpx

    headers = {"Authorization": f"Bearer {LITELLM_MASTER_KEY}"}
    if user_info:
        headers["X-User-ID"] = user_info.get("user_id", "")

    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{LITELLM_PROXY_URL}{path}"
        if method == "GET":
            resp = await client.get(url, headers=headers)
        elif method == "POST":
            resp = await client.post(url, headers=headers, json=body)
        elif method == "DELETE":
            resp = await client.delete(url, headers=headers)
        elif method == "PUT":
            resp = await client.put(url, headers=headers, json=body)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported method: {method}")

        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()


# ── RBAC Endpoints ──────────────────────────────────────────────────


@app.post("/api/roles/assign")
async def assign_role(
    role: UserRole,
    user_info: dict = Depends(_require_permission("manage_roles")),
):
    from markom_gateway.admin_service.markom_admin.rbac import RBACService

    success = RBACService.set_user_role(
        user_external_id=role.user_id,
        role=role.role,
        email=role.email,
        display_name=role.display_name,
        team_id=role.team_id,
        granted_by=user_info["user_id"],
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to assign role")
    return {"status": "assigned", "user_id": role.user_id, "role": role.role}


@app.get("/api/roles/list")
async def list_roles(
    team_id: Optional[str] = None,
    user_info: dict = Depends(_require_permission("manage_roles")),
):
    from markom_gateway.admin_service.markom_admin.rbac import RBACService

    users = RBACService.list_users(team_id=team_id)
    return {"users": users}


@app.delete("/api/roles/remove")
async def remove_role(
    user_id: str,
    team_id: Optional[str] = None,
    user_info: dict = Depends(_require_permission("manage_roles")),
):
    from markom_gateway.admin_service.markom_admin.rbac import RBACService

    success = RBACService.remove_user(user_id, team_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "removed", "user_id": user_id}


@app.get("/api/roles/check")
async def check_permission(
    user_id: str,
    permission: str,
    team_id: Optional[str] = None,
    user_info: dict = Depends(_require_auth),
):
    from markom_gateway.admin_service.markom_admin.rbac import RBACService

    has_perm = RBACService.has_permission(user_id, permission, team_id)
    role = RBACService.get_user_role(user_id, team_id)
    return {
        "user_id": user_id,
        "permission": permission,
        "has_permission": has_perm,
        "role": role,
    }


# ── Audit Endpoints ─────────────────────────────────────────────────


@app.get("/api/audit/records")
async def get_audit_records(
    user_id: Optional[str] = None,
    team_id: Optional[str] = None,
    model: Optional[str] = None,
    status: Optional[str] = None,
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
    limit: int = 100,
    offset: int = 0,
    user_info: dict = Depends(_require_permission("view_audit")),
):
    from markom_gateway.hooks.audit_logger import MarkomAuditLogger

    records = MarkomAuditLogger.get_audit_records(
        limit=limit,
        offset=offset,
        user_id=user_id,
        team_id=team_id,
        model=model,
        status=status,
        start_time=start_time,
        end_time=end_time,
    )
    return {"records": records, "count": len(records)}


@app.get("/api/audit/stats")
async def get_audit_stats(
    user_info: dict = Depends(_require_permission("view_audit")),
):
    from markom_gateway.hooks.audit_logger import MarkomAuditLogger

    return MarkomAuditLogger.get_stats()


@app.get("/api/audit/export")
async def export_audit(
    format: str = "csv",
    user_id: Optional[str] = None,
    team_id: Optional[str] = None,
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
    user_info: dict = Depends(_require_permission("export_audit")),
):
    from markom_gateway.hooks.audit_logger import MarkomAuditLogger

    if format == "csv":
        csv_data = MarkomAuditLogger.export_records_csv(
            user_id=user_id,
            team_id=team_id,
            start_time=start_time,
            end_time=end_time,
        )
        from fastapi.responses import Response

        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit_export.csv"},
        )
    else:
        records = MarkomAuditLogger.get_audit_records(
            limit=10000,
            user_id=user_id,
            team_id=team_id,
            start_time=start_time,
            end_time=end_time,
        )
        return {"records": records}


@app.post("/api/audit/purge")
async def purge_audit_records(
    retention_days: int = 90,
    user_info: dict = Depends(_require_permission("export_audit")),
):
    from markom_gateway.hooks.audit_logger import MarkomAuditLogger

    deleted = MarkomAuditLogger.purge_old_records(retention_days)
    return {"deleted": deleted, "retention_days": retention_days}


# ── Cache Endpoints ─────────────────────────────────────────────────


@app.post("/api/cache/purge")
async def purge_cache(
    request: CachePurgeRequest,
    user_info: dict = Depends(_require_permission("manage_roles")),
):
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Set confirm=true to purge cache")
    from markom_gateway.hooks.semantic_cache import MarkomSemanticCache

    MarkomSemanticCache.purge_cache()
    return {"status": "purged"}


# ── Key Management (proxy to LiteLLM) ───────────────────────────────


@app.post("/api/keys/generate")
async def generate_key(
    request: Request,
    user_info: dict = Depends(_require_permission("create_key")),
):
    body = await request.json()
    return await _proxy_to_litellm("POST", "/key/generate", body, user_info)


@app.get("/api/keys")
async def list_keys(
    user_info: dict = Depends(_require_permission("view_key")),
):
    return await _proxy_to_litellm("GET", "/key/list", user_info=user_info)


@app.delete("/api/keys/{key_hash}")
async def delete_key(
    key_hash: str,
    user_info: dict = Depends(_require_permission("delete_key")),
):
    return await _proxy_to_litellm("DELETE", f"/key/delete?key={key_hash}", user_info=user_info)


@app.post("/api/keys/update")
async def update_key(
    request: Request,
    user_info: dict = Depends(_require_permission("update_key")),
):
    body = await request.json()
    return await _proxy_to_litellm("POST", "/key/update", body, user_info)


# ── Team Management (proxy to LiteLLM) ──────────────────────────────


@app.post("/api/teams/new")
async def create_team(
    request: Request,
    user_info: dict = Depends(_require_permission("create_team")),
):
    body = await request.json()
    return await _proxy_to_litellm("POST", "/team/new", body, user_info)


@app.get("/api/teams")
async def list_teams(
    user_info: dict = Depends(_require_permission("view_team")),
):
    return await _proxy_to_litellm("GET", "/team/list", user_info=user_info)


@app.delete("/api/teams/{team_id}")
async def delete_team(
    team_id: str,
    user_info: dict = Depends(_require_permission("delete_team")),
):
    return await _proxy_to_litellm("DELETE", f"/team/delete?team_id={team_id}", user_info=user_info)


@app.post("/api/teams/update")
async def update_team(
    request: Request,
    user_info: dict = Depends(_require_permission("update_team")),
):
    body = await request.json()
    return await _proxy_to_litellm("POST", "/team/update", body, user_info)


# ── Dashboard Routers ───────────────────────────────────────────────

app.include_router(auth_router)
app.include_router(home_router)
app.include_router(cost_router)
app.include_router(usage_router)
app.include_router(providers_router)
app.include_router(guardrails_router)
app.include_router(accounts_router)
app.include_router(settings_router)


# ── Health ──────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "markom-gateway-admin"}


@app.get("/", response_class=HTMLResponse)
async def root():
    index_path = UI_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path), media_type="text/html")
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>MarKom Gateway Admin</title>
        <style>
            :root { --primary: #120505; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                   margin: 0; padding: 40px; background: #fafafa; color: #333; }
            h1 { color: var(--primary); }
            .endpoint { margin: 8px 0; padding: 8px 12px; background: #fff;
                       border: 1px solid #ddd; border-radius: 4px; }
            .method { font-weight: bold; color: var(--primary); }
        </style>
    </head>
    <body>
        <h1>MarKom Gateway Admin Service</h1>
        <p>RBAC-gated management endpoints for MarKom Gateway.</p>
        <h2>Endpoints</h2>
        <div class="endpoint"><span class="method">GET</span> /api/auth/me — Current user profile</div>
        <div class="endpoint"><span class="method">GET</span> /api/roles/list — List users and roles</div>
        <div class="endpoint"><span class="method">POST</span> /api/roles/assign — Assign a role to a user</div>
        <div class="endpoint"><span class="method">DELETE</span> /api/roles/remove — Remove a user role</div>
        <div class="endpoint"><span class="method">GET</span> /api/roles/check — Check a user's permission</div>
        <div class="endpoint"><span class="method">GET</span> /api/settings/roles — List role templates</div>
        <div class="endpoint"><span class="method">POST</span> /api/settings/roles — Create custom role</div>
        <div class="endpoint"><span class="method">PUT</span> /api/settings/roles/{slug} — Update role template</div>
        <div class="endpoint"><span class="method">DELETE</span> /api/settings/roles/{slug} — Delete custom role</div>
        <div class="endpoint"><span class="method">GET</span> /api/accounts — List user accounts</div>
        <div class="endpoint"><span class="method">POST</span> /api/accounts — Create account</div>
        <div class="endpoint"><span class="method">GET</span> /api/home/summary — Home tab summary</div>
        <div class="endpoint"><span class="method">GET</span> /api/cost/summary — Cost summary</div>
        <div class="endpoint"><span class="method">GET</span> /api/usage/requests — Usage requests</div>
        <div class="endpoint"><span class="method">GET</span> /api/providers/health — Provider health</div>
        <div class="endpoint"><span class="method">GET</span> /api/guardrails/audit — Audit trail</div>
        <div class="endpoint"><span class="method">GET</span> /api/audit/records — Query audit records</div>
        <div class="endpoint"><span class="method">GET</span> /api/audit/stats — Get audit statistics</div>
        <div class="endpoint"><span class="method">POST</span> /api/cache/purge — Purge semantic cache</div>
        <div class="endpoint"><span class="method">POST</span> /api/keys/generate — Generate an API key</div>
        <div class="endpoint"><span class="method">GET</span> /api/keys — List API keys</div>
        <div class="endpoint"><span class="method">POST</span> /api/teams/new — Create a team</div>
        <div class="endpoint"><span class="method">GET</span> /api/teams — List teams</div>
        <div class="endpoint"><span class="method">GET</span> /health — Health check</div>
    </body>
    </html>
    """


@app.get("/dashboard")
async def dashboard():
    index_path = UI_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path), media_type="text/html")
    raise HTTPException(status_code=404, detail="Dashboard not deployed yet")
