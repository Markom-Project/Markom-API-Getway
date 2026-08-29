# MarKom Gateway — Analytics Dashboard & RBAC Implementation Roadmap

**Date:** 2026-08-29
**Base:** `markom_gateway/admin_service/` — FastAPI RBAC admin sitting in front of LiteLLM
**Brand:** "MarKom Gateway", primary color `#120505`
**Goal:** One dashboard, two experiences — Admin sees every tab; Employee/Viewer sees only what their role permits.

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    MarKom Gateway Admin Service              │
│                      (FastAPI, port 8000)                    │
├─────────────────────────────────────────────────────────────┤
│  /api/auth/me          ← returns user's role + tabs         │
│  /api/settings/roles   ← admin configures role templates    │
│  /api/accounts         ← admin CRUD users                   │
│  /api/home             ← home tab data                      │
│  /api/cost             ← cost tab data                      │
│  /api/usage            ← usage tab data                     │
│  /api/providers        ← provider health scores             │
│  /api/guardrails       ← guardrail triggers + audit trail   │
├─────────────────────────────────────────────────────────────┤
│  RBAC Layer (rbac.py + tab_matrix.py)                       │
│    ├── markom_users          (user identity + role)          │
│    ├── markom_roles          (team-scoped role overrides)    │
│    ├── markom_roles_config   (custom role definitions)       │
│    └── markom_role_templates (role → tabs + permissions)     │
├─────────────────────────────────────────────────────────────┤
│  LiteLLM Proxy (port 4000)                                  │
│    ├── /global/spend/*        (cost data)                   │
│    ├── /global/activity/*     (usage data)                  │
│    ├── /health/*              (provider health)             │
│    ├── /key/*, /team/*        (management)                  │
│    └── /spend/logs/v2         (detailed logs)               │
├─────────────────────────────────────────────────────────────┤
│  MarKom Gateway Hooks                                       │
│    ├── audit_logger.py    (Postgres audit trail)            │
│    ├── health_router.py   (Redis health metrics)            │
│    ├── semantic_cache.py  (FAISS/Pinecone cache)            │
│    └── pii_guardrail.py   (PII detection)                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Data Model

### 2.1 Existing Tables (already created)

**`markom_users`**
| Column | Type | Notes |
|--------|------|-------|
| id | BIGSERIAL PK | |
| external_id | TEXT UNIQUE | User's external ID |
| email | TEXT | |
| display_name | TEXT | |
| role | TEXT DEFAULT 'viewer' | Legacy — being replaced by role_slug FK |
| api_key_hash | TEXT | SHA-256 truncated |
| tab_overrides | JSONB DEFAULT '[]' | Per-user tab grants beyond role |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

**`markom_audit_log`**
| Column | Type | Notes |
|--------|------|-------|
| id | BIGSERIAL PK | |
| timestamp | TIMESTAMPTZ | |
| request_id | TEXT UNIQUE | |
| user_id | TEXT | |
| team_id | TEXT | |
| model | TEXT | |
| provider | TEXT | |
| prompt_tokens | INT | |
| completion_tokens | INT | |
| total_tokens | INT | |
| cost_usd | FLOAT | |
| latency_ms | FLOAT | |
| status | TEXT | 'success' or 'failure' |
| error_message | TEXT | |
| guardrail_results | JSONB | |
| routing_decision | JSONB | |
| metadata | JSONB | |

### 2.2 New Tables (to create)

**`markom_roles_config`** — custom role definitions
| Column | Type | Notes |
|--------|------|-------|
| id | BIGSERIAL PK | |
| slug | TEXT UNIQUE | 'admin', 'team_lead', 'developer', 'viewer', 'billing_auditor' |
| display_name | TEXT | 'Admin', 'Team Lead', etc. |
| description | TEXT | Human-readable |
| is_system | BOOLEAN DEFAULT false | true for 'admin' (can't delete) |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

**`markom_role_templates`** — what each role can access
| Column | Type | Notes |
|--------|------|-------|
| id | BIGSERIAL PK | |
| role_slug | TEXT UNIQUE FK | → markom_roles_config.slug |
| tabs | JSONB DEFAULT '[]' | ["home","cost","usage"] |
| permissions | JSONB DEFAULT '[]' | ["create_key","view_audit",...] |
| updated_at | TIMESTAMPTZ | |
| updated_by | TEXT | Admin who last edited |

### 2.3 Seed Data

On first startup, `_ensure_rbac_tables()` seeds defaults:

```python
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
            "manage_users", "manage_roles", "view_budgets", "update_budgets"
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
            "view_budgets", "update_budgets"
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
```

---

## 3. Tab Visibility Matrix (Admin-Configurable)

### 3.1 Default Matrix (from seed data)

```
              Home   Cost   Usage   Providers   Guardrails   Accounts   Settings
Admin         [x]    [x]    [x]     [x]         [x]          [x]        [x]
Team Lead     [x]    [x]    [x]     [ ]         [ ]          [ ]        [ ]
Developer     [x]    [ ]    [x]     [ ]         [ ]          [ ]        [ ]
Viewer        [x]    [ ]    [ ]     [ ]         [ ]          [ ]        [ ]
```

### 3.2 Admin Can Modify

- Create custom roles (e.g. "Billing Auditor", "Compliance Officer")
- Check/uncheck tabs per role
- Check/uncheck fine-grained permissions per role
- Delete custom roles (can't delete "admin" system role)

### 3.3 Per-User Overrides

On top of role templates, admin can grant individual users extra tabs:
- Stored in `markom_users.tab_overrides` as `["cost", "providers"]`
- Final access = `role_template.tabs + user_overrides.tabs`

---

## 4. API Endpoints

### 4.1 Auth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/auth/me` | Any user | Returns `{user_id, email, role, tabs, permissions}` |

### 4.2 Role Template Management (Admin only)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/settings/roles` | `manage_roles` | List all roles with templates |
| `POST` | `/api/settings/roles` | `manage_roles` | Create custom role |
| `PUT` | `/api/settings/roles/{slug}` | `manage_roles` | Update role tabs + permissions |
| `DELETE` | `/api/settings/roles/{slug}` | `manage_roles` | Delete custom role (not system) |

### 4.3 Account Management (Admin only)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/accounts` | `manage_users` | List all users with role, team, status |
| `POST` | `/api/accounts` | `manage_users` | Create user (role, team, tab overrides) |
| `PUT` | `/api/accounts/{user_id}` | `manage_users` | Update user (role, team, tabs, status) |
| `POST` | `/api/accounts/{user_id}/disable` | `manage_users` | Soft-disable account |
| `POST` | `/api/accounts/{user_id}/remove` | `manage_users` | Hard delete (audit-logged) |

### 4.4 Dashboard Tab Endpoints

| Method | Path | Tabs | Description |
|--------|------|------|-------------|
| `GET` | `/api/home/summary` | home | Spend summary, health, activity |
| `GET` | `/api/cost/summary` | cost | Total spend by time range |
| `GET` | `/api/cost/by-model` | cost | Spend per model |
| `GET` | `/api/cost/by-team` | cost | Spend per team |
| `GET` | `/api/cost/by-key` | cost | Spend per API key |
| `GET` | `/api/cost/trend` | cost | Spend over time |
| `GET` | `/api/cost/export` | cost | CSV export |
| `GET` | `/api/usage/requests` | usage | Request volume over time |
| `GET` | `/api/usage/latency` | usage | Latency distribution |
| `GET` | `/api/usage/errors` | usage | Error breakdown |
| `GET` | `/api/usage/cache-hits` | usage | Cache hit rate |
| `GET` | `/api/providers/health` | providers | Health scores per provider |
| `GET` | `/api/providers/routing-log` | providers | Recent routing decisions |
| `POST` | `/api/providers/{model}/toggle` | providers | Enable/disable provider |
| `GET` | `/api/guardrails/triggers` | guardrails | Guardrail trigger log |
| `GET` | `/api/guardrails/audit` | guardrails | Audit trail viewer |
| `GET` | `/api/guardrails/audit/export` | guardrails | Export audit as CSV |

### 4.5 Existing Endpoints (unchanged)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/roles/assign` | Assign role to user |
| `GET` | `/api/roles/list` | List users |
| `DELETE` | `/api/roles/remove` | Remove user |
| `GET` | `/api/roles/check` | Check permission |
| `GET` | `/api/audit/records` | Query audit records |
| `GET` | `/api/audit/stats` | Audit statistics |
| `GET` | `/api/audit/export` | Export audit CSV |
| `POST` | `/api/cache/purge` | Purge semantic cache |

---

## 5. Frontend Architecture

### 5.1 Tech Stack

- **HTML/CSS/JS** — no build step, served by FastAPI
- **Chart.js** — charts and graphs
- **Fetch API** — data loading
- **CSS Variables** — brand theming

### 5.2 Directory Structure

```
markom_gateway/admin_service/markom_admin/ui/
├── index.html                 # Dashboard shell (sidebar + content)
├── app.js                     # SPA router, auth, tab switching
├── api.js                     # API client wrapper
├── theme.js                   # #120505 brand constants
├── static/
│   ├── css/
│   │   └── dashboard.css      # All styles
│   └── js/
│       ├── chart.min.js       # Chart.js (vendored)
│       └── chart-setup.js     # Chart.js defaults (brand colors)
├── pages/
│   ├── home.js                # Home tab
│   ├── cost.js                # Cost tab
│   ├── usage.js               # Usage tab
│   ├── providers.js           # Providers tab
│   ├── guardrails.js          # Guardrails tab
│   ├── accounts.js            # Accounts tab (admin only)
│   └── settings.js            # Settings tab (role template manager)
└── components/
    ├── sidebar.js             # Sidebar nav component
    ├── header.js              # Top bar component
    ├── charts.js              # Reusable chart wrappers
    ├── tables.js              # Reusable data tables
    ├── modals.js              # Reusable modals
    └── toast.js               # Toast notifications
```

### 5.3 Auth Flow

```
1. User opens dashboard → index.html loads
2. app.js calls GET /api/auth/me
3. If 401 → redirect to LiteLLM login
4. If 200 → cache {role, tabs, permissions} in sessionStorage
5. Render sidebar with only allowed tabs
6. Load first allowed tab (usually Home)
```

### 5.4 Tab Access Enforcement

**Frontend:**
- Sidebar only shows tabs the user has access to
- SPA router checks tab slug against cached tabs list
- If user navigates to unauthorized tab → redirect to Home with toast "You don't have access to this page"

**Backend:**
- Every `/api/<tab>/*` route calls `has_tab_access(user_id, tab_slug)`
- Returns 403 if user doesn't have access
- Never trust frontend-only checks

---

## 6. UI Pages — Detailed Specs

### 6.1 Home

**Layout:** 4 stat cards + 1 chart + 1 health panel

| Section | Data Source | What It Shows |
|---------|------------|---------------|
| Total Spend (today/7d/30d) | `/global/spend` | Dollar amount with period selector |
| Total Requests | `/global/activity` | Request count with period selector |
| Active Providers | `/health` | Count of healthy endpoints |
| Cache Hit Rate | `/global/activity/cache_hits` | Percentage |
| Request Activity Chart | `/global/activity` | Line chart, requests/day |
| Provider Health Panel | `/health/latest` | Status per provider (green/red) |

**Charts:** Line chart with `#120505` as primary color, neutral grays for secondary.

### 6.2 Cost

**Layout:** Time range picker + 4 breakdown tables + trend chart + export button

| Section | Data Source | What It Shows |
|---------|------------|---------------|
| Spend Trend | `/global/spend/logs` | Line chart, spend over time |
| By Model | `/global/spend/models` | Table: model, spend, % of total |
| By Team | `/global/spend/teams` | Table: team, daily spend |
| By API Key | `/global/spend/keys` | Table: key alias, spend |
| By Provider | `/global/spend/provider` | Pie chart: provider, spend |
| Export CSV | `/global/spend/report` | Download button (admin + team_lead only) |

### 6.3 Usage / Requests

**Layout:** Time range picker + 4 panels

| Section | Data Source | What It Shows |
|---------|------------|---------------|
| Request Volume | `/global/activity` | Bar chart, requests/day |
| Latency Distribution | `/spend/logs/v2` | p50/p95/p99 per model |
| Error Breakdown | `/global/activity/exceptions` | Errors by type over time |
| Cache Hit Rate | `/global/activity/cache_hits` | Hits vs misses trend |

### 6.4 Providers & Routing

**Layout:** Health score table + routing log + toggle controls

| Section | Data Source | What It Shows |
|---------|------------|---------------|
| Health Scores | `/health` + Redis | Table: provider, model, score, latency, errors |
| Routing Log | Audit trail `routing_decision` | Last 50 routing decisions |
| Toggle Provider | `/model/block` or `/model/unblock` | Enable/disable buttons (admin only) |

### 6.5 Guardrails & Compliance

**Layout:** Trigger log + audit trail viewer + export

| Section | Data Source | What It Shows |
|---------|------------|---------------|
| Guardrail Triggers | Audit trail `guardrail_results` | PII redactions, blocks, flags |
| Audit Trail | `/api/audit/records` | Searchable/filterable log table |
| Retention Policy | Config | Current DPDPA retention window |
| Export | `/api/audit/export` | CSV/JSON download (admin only) |

### 6.6 Accounts (Admin only)

**Layout:** User table + CRUD modals

| Section | Data Source | What It Shows |
|---------|------------|---------------|
| User List | `/api/accounts` | Name, email, role, team, status, last active |
| Create Modal | POST `/api/accounts` | Form: name, email, role dropdown, team, tab overrides |
| Edit Modal | PUT `/api/accounts/{id}` | Same form + disable toggle |
| Disable | POST `/api/accounts/{id}/disable` | Soft-disable with confirmation |
| Remove | POST `/api/accounts/{id}/remove` | Hard delete with typed confirmation |

### 6.7 Settings (Admin only)

**Layout:** Role list + edit form with checkbox matrices

| Section | What It Shows |
|---------|---------------|
| Role List | Table: role name, description, user count, actions |
| Create Role | Modal: slug, display name, description |
| Edit Role | Tabs checkbox matrix + Permissions checkbox matrix |
| Delete Role | Confirmation (can't delete system roles) |

**Tab Checkbox Matrix:**
```
              Home   Cost   Usage   Providers   Guardrails   Accounts   Settings
Admin         [x]    [x]    [x]     [x]         [x]          [x]        [x]
Team Lead     [x]    [x]    [x]     [ ]         [ ]          [ ]        [ ]
```

**Permission Checkbox Matrix:**
```
Key:      [View] [Create] [Update] [Delete]
Team:     [View] [Create] [Update] [Delete]
Audit:    [View] [Export]
Budgets:  [View] [Update]
Accounts: [Manage Users] [Manage Roles]
```

---

## 7. Brand Color Application

All UI elements use `#120505` as:

| Element | CSS Property |
|---------|-------------|
| Sidebar background | `background: #120505` |
| Active nav item | `background: rgba(255,255,255,0.1)`, `border-left: 3px solid #120505` |
| Chart primary series | `color: #120505` |
| Primary buttons | `background: #120505; color: white` |
| Table header | `background: #120505; color: white` |
| Modal header | `background: #120505; color: white` |
| Links | `color: #120505` |
| Focus rings | `box-shadow: 0 0 0 2px rgba(18,5,5,0.3)` |

CSS variable: `--brand: #120505;`

---

## 8. Implementation Phases

### Phase 1 — Backend Core (RBAC + Auth)
| # | Task | Files | Est. Lines |
|---|------|-------|-----------|
| 1 | Create new DB tables + seed defaults | `rbac.py` | +60 |
| 2 | Extend rbac.py — DB-backed role templates, custom role CRUD | `rbac.py` | +120 |
| 3 | Create tab_matrix.py — tab/permission resolution | `tab_matrix.py` (new) | +40 |
| 4 | Create routes/auth.py — GET /api/auth/me | `routes/auth.py` (new) | +30 |

### Phase 2 — Backend Routes (7 tab endpoints)
| # | Task | Files | Est. Lines |
|---|------|-------|-----------|
| 5 | Create routes/home.py | `routes/home.py` (new) | +80 |
| 6 | Create routes/cost.py | `routes/cost.py` (new) | +120 |
| 7 | Create routes/usage.py | `routes/usage.py` (new) | +100 |
| 8 | Create routes/providers.py | `routes/providers.py` (new) | +80 |
| 9 | Create routes/guardrails.py | `routes/guardrails.py` (new) | +80 |
| 10 | Create routes/accounts.py | `routes/accounts.py` (new) | +150 |
| 11 | Create routes/settings.py | `routes/settings.py` (new) | +80 |
| 12 | Update main.py — mount routers + serve UI | `main.py` | +30 |

### Phase 3 — Frontend (Dashboard UI)
| # | Task | Files | Est. Lines |
|---|------|-------|-----------|
| 13 | Create UI shell — index.html | `ui/index.html` (new) | +200 |
| 14 | Create app.js — SPA router + auth | `ui/app.js` (new) | +150 |
| 15 | Create api.js — API client | `ui/api.js` (new) | +60 |
| 16 | Create theme.js — brand constants | `ui/theme.js` (new) | +15 |
| 17 | Create dashboard.css — brand theme | `ui/static/css/dashboard.css` (new) | +350 |
| 18 | Create chart-setup.js — Chart.js defaults | `ui/static/js/chart-setup.js` (new) | +30 |
| 19 | Create pages/home.js | `ui/pages/home.js` (new) | +120 |
| 20 | Create pages/cost.js | `ui/pages/cost.js` (new) | +150 |
| 21 | Create pages/usage.js | `ui/pages/usage.js` (new) | +120 |
| 22 | Create pages/providers.js | `ui/pages/providers.js` (new) | +100 |
| 23 | Create pages/guardrails.js | `ui/pages/guardrails.js` (new) | +100 |
| 24 | Create pages/accounts.js | `ui/pages/accounts.js` (new) | +180 |
| 25 | Create pages/settings.js | `ui/pages/settings.js` (new) | +200 |
| 26 | Create shared components | `ui/components/*.js` (6 new) | +300 |

### Phase 4 — Verify & Ship
| # | Task | Notes |
|---|------|-------|
| 27 | Test full flow | Login, tab visibility, role CRUD, account management |
| 28 | Test access control | Employee can't see Cost; direct URL redirect works |
| 29 | Test audit trail | Account create/edit/disable/delete all logged |
| 30 | Commit + push to main | |

---

## 9. Acceptance Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | New employee sees only Home tab | Create user with role=employee, login, check sidebar |
| 2 | Employee hitting /cost by URL redirects to Home | Navigate to /cost as employee |
| 3 | Admin sees all 7 tabs | Login as admin |
| 4 | Granting employee override to "Usage" shows that tab | Edit employee, add tab override |
| 5 | Custom role "Billing Auditor" visible in Settings | Create role, verify it appears |
| 6 | Custom role gets correct tabs | Assign to user, verify sidebar |
| 7 | All account actions audit-logged | Check audit trail after create/edit/disable/delete |
| 8 | All charts use #120505 as primary | Visual inspection |
| 9 | Role template changes apply immediately | Edit role, verify user's next login reflects it |
| 10 | Can't delete system "admin" role | Try delete, expect error |

---

## 10. Migration Notes

- The existing `markom_users.role` column is kept for backward compatibility
- New system uses `markom_roles_config.slug` as the source of truth
- `rbac.py` maps old role strings to new slugs transparently
- No data migration needed — existing users keep their roles, which map to the seeded templates
