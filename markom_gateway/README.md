# MarKom Gateway

MarKom Gateway includes an independent OpenRouter-backed inference runtime and existing administration and governance services that still integrate with LiteLLM.

## Standalone inference service

The standalone runtime is an independent OpenAI-compatible HTTP API backed by OpenRouter. It supports `GET /v1/models`, `POST /v1/chat/completions`, streaming responses, and a gateway bearer key. This is the first step toward replacing the existing LiteLLM dependency; the admin service and existing hooks still depend on LiteLLM and are not standalone yet.

Set `MARKOM_MASTER_KEY` and `OPENROUTER_API_KEY`, then start the runtime with Docker Compose:

```bash
docker compose -f markom_gateway/docker-compose.standalone.yml up --build
```

Send OpenAI-compatible requests to `http://localhost:4000/v1` using `MARKOM_MASTER_KEY` as the client API key. The `model` value is passed to OpenRouter unchanged.

```bash
curl http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $MARKOM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"openai/gpt-4o-mini","messages":[{"role":"user","content":"Hello"}]}'
```

### Model routing and fallbacks

Configure `OPENAI_API_KEY` to enable direct OpenAI routing. `MARKOM_MODEL_ROUTES` maps a gateway model name to an ordered list of provider/model targets. The gateway tries the next target on a network error, HTTP 429, or HTTP 5xx response. It does not retry client errors.

```bash
export MARKOM_MODEL_ROUTES='{"assistant":{"targets":[{"provider":"openai","model":"gpt-4o-mini"},{"provider":"openrouter","model":"openai/gpt-4o-mini"}]}}'
```

Requests use `"model":"assistant"`, and `GET /v1/models` returns configured route names. OpenRouter remains the default for model IDs without a configured route.

## Architecture

```
markom_gateway/
├── proxy_config.yaml              # LiteLLM config: models, guardrails, callbacks
├── hooks/
│   ├── semantic_cache.py          # FAISS/Pinecone vector similarity caching
│   ├── health_router.py           # Redis-backed dynamic provider routing
│   ├── audit_logger.py            # DPDPA-compliant audit trail (Postgres)
│   └── pii_guardrail.py           # PII detection and redaction
├── admin_service/
│   ├── main.py                    # FastAPI app: RBAC + dashboard API
│   ├── routes/
│   │   ├── auth.py                # GET /api/auth/me
│   │   ├── home.py                # Home tab data
│   │   ├── cost.py                # Cost analytics (6 endpoints)
│   │   ├── usage.py               # Usage analytics (4 endpoints)
│   │   ├── providers.py           # Provider health + routing (3 endpoints)
│   │   ├── guardrails.py          # Trigger log + audit viewer (3 endpoints)
│   │   ├── accounts.py            # User CRUD (5 endpoints)
│   │   ├── settings.py            # Role template management (5 endpoints)
│   │   ├── compliance.py          # DPDPA data principal export/delete (4 endpoints)
│   │   └── incidents.py           # Anomalous access + guardrail violation alerts
│   └── markom_admin/
│       ├── rbac.py                # DB-backed role templates + per-user overrides
│       ├── tab_matrix.py          # Single source of truth for tab/permission resolution
│       └── ui/                    # SPA dashboard (vanilla HTML/CSS/JS)
├── Dockerfile
├── requirements.txt
└── README.md
```

## Quick Start

### Option 1: Docker Compose (recommended)

```bash
# Clone
git clone https://github.com/arpanchakraborty23/Markom-API-Getway.git
cd Markom-API-Getway

# Edit .env — at minimum set:
#   OPENAI_API_KEY=sk-...
#   MARKOM_MASTER_KEY=sk-markom-secret-key-change-me

# Start all services
./start.sh
```

| Service | URL | Default Login |
|---------|-----|---------------|
| **Dashboard** | http://localhost:8000/dashboard | API key from `.env` |
| **LiteLLM Proxy** | http://localhost:4000 | Bearer token |
| **Grafana** | http://localhost:3000 | admin / admin |
| **Prometheus** | http://localhost:9090 | — |

### Option 2: Local Python

```bash
# Start only Postgres and Redis
docker compose --profile postgres --profile redis up -d

# Install dependencies
python -m venv .venv && source .venv/bin/activate
pip install litellm[proxy]
pip install -r markom_gateway/requirements.txt

# Terminal 1: Start LiteLLM proxy
litellm --config markom_gateway/proxy_config.yaml --port 4000

# Terminal 2: Start admin service
uvicorn markom_gateway.admin_service.main:app --port 8000 --reload

# Open http://localhost:8000/dashboard
```

## Environment Variables

See **[LOCAL_DEV.md](LOCAL_DEV.md)** for the full reference with purpose descriptions, defaults, and local dev tips.

### Minimum required for local testing

```bash
GOOGLE_API_KEY=your-gemini-api-key
OPENAI_API_KEY=sk-your-key-here
MARKOM_MASTER_KEY=sk-markom-secret-key-change-me
MARKOM_DATABASE_URL=postgresql://llmproxy:dbpassword9090@db:5432/litellm
MARKOM_REDIS_URL=redis://redis:6379
```

## Features

### Semantic Caching
Caches near-duplicate prompts using vector similarity search (FAISS). Embeddings are generated via Gemini API through LiteLLM's interface — no local embedding models needed. Returns cached response without calling the LLM on cache hit. Configurable threshold (default: 0.95), per-model skip list, manual purge endpoint.

### Health-Based Rolling Routing
Records per-provider latency, error rate, and timeout rate in Redis. Rewrites routing to prefer the healthiest provider. Rolling 5-minute scoring window, 2% exploration factor.

### DPDPA-Compliant Audit Trail
Every request produces an immutable record with: timestamp, user/team, model, tokens, cost, latency, guardrail results, routing decision, **purpose context** (team/feature/use_case), and **data principal ID**. Configurable per-team content redaction, separate retention windows for metadata (90d) vs prompt content (30d), auto-purge on startup.

### RBAC with Role Templates
Four default roles: `admin`, `team_lead`, `developer`, `viewer`. Admins can create custom roles via the dashboard Settings tab. Each role configures which tabs the user sees AND fine-grained permissions (manage_users, export_audit, etc.). Per-user tab overrides layer on top of role templates.

### Compliance Endpoints
- `POST /api/compliance/principal/export` — export all records for a data principal
- `POST /api/compliance/principal/delete` — redact prompt/response content (preserve metadata)
- `POST /api/compliance/retention/purge` — manual retention purge
- `GET /api/compliance/retention/config` — view retention settings

### Incident Detection
- Anomalous access patterns (high-volume users)
- Repeated guardrail violations per user
- High error rate users
- Summary endpoint for tab banners

### PII Guardrail
Optional PII detection and redaction in prompts. Supports email, phone, SSN, credit card, IP, Aadhaar, PAN patterns. Can block or log-only.

## Dashboard Tabs

| Tab | What it shows | Who sees it |
|-----|--------------|-------------|
| **Home** | Spend summary, provider health, cache rate | All roles |
| **Cost** | Spend trend, by model/team/key, CSV export | Team Lead, Admin |
| **Usage** | Request volume, latency percentiles, error rate | Developer+, Admin |
| **Providers** | Health scores, routing decisions, model toggle | Admin |
| **Guardrails** | PII triggers, audit trail viewer, CSV export | Admin |
| **Accounts** | User CRUD, disable/remove with audit logging | Admin |
| **Settings** | Role template manager (create/edit/delete roles) | Admin |

## API Endpoints

| Method | Endpoint | Permission | Description |
|--------|----------|------------|-------------|
| `GET` | `/api/auth/me` | auth | Current user profile + tabs + permissions |
| `GET` | `/api/home/summary` | tab access | Spend, providers, cache rate |
| `GET` | `/api/cost/summary` | tab access | Total spend, daily breakdown |
| `GET` | `/api/cost/by-model` | tab access | Spend grouped by model |
| `GET` | `/api/cost/by-team` | tab access | Spend grouped by team |
| `GET` | `/api/cost/export` | tab access | CSV export of cost data |
| `GET` | `/api/usage/requests` | tab access | Request volume by date |
| `GET` | `/api/usage/latency` | tab access | Latency percentiles by model |
| `GET` | `/api/usage/errors` | tab access | Error count by date |
| `GET` | `/api/providers/health` | tab access | Provider health scores |
| `GET` | `/api/guardrails/triggers` | tab access | PII guardrail trigger log |
| `GET` | `/api/guardrails/audit` | tab access | Audit trail viewer |
| `GET` | `/api/guardrails/audit/export` | `export_audit` | CSV export of audit trail |
| `GET` | `/api/accounts` | `manage_users` | List user accounts |
| `POST` | `/api/accounts` | `manage_users` | Create account |
| `PUT` | `/api/accounts/{id}` | `manage_users` | Update account |
| `POST` | `/api/accounts/{id}/disable` | `manage_users` | Disable account |
| `POST` | `/api/accounts/{id}/remove` | `manage_users` | Remove account (audit preserved) |
| `GET` | `/api/settings/roles` | tab access | List role templates |
| `POST` | `/api/settings/roles` | `manage_roles` | Create custom role |
| `PUT` | `/api/settings/roles/{slug}` | `manage_roles` | Update role template |
| `DELETE` | `/api/settings/roles/{slug}` | `manage_roles` | Delete custom role |
| `POST` | `/api/compliance/principal/export` | `view_audit` | DPDPA data export |
| `POST` | `/api/compliance/principal/delete` | `export_audit` | DPDPA data erasure |
| `POST` | `/api/compliance/retention/purge` | `export_audit` | Manual retention purge |
| `GET` | `/api/incidents/anomalous-access` | tab access | High-volume user detection |
| `GET` | `/api/incidents/guardrail-violations` | tab access | Repeated violation detection |
| `GET` | `/api/incidents/summary` | tab access | Aggregate incident counts |

## Upgrading the existing LiteLLM integration

The `markom_gateway/` directory is additive — no LiteLLM core files are modified. To upgrade:

1. Update the `litellm` version in `requirements.txt` or `pyproject.toml`
2. Rebuild: `docker compose --profile core up -d --build`
3. Hooks continue to work via the `CustomGuardrail` and `CustomLogger` plugin APIs

## Documentation

- **[LOCAL_DEV.md](LOCAL_DEV.md)** — Full .env reference, local setup, testing guide
- **[SUB_PROCESSORS.md](SUB_PROCESSORS.md)** — Third-party service list for compliance reviews
- **[DASHBOARD_ROADMAP.md](markom_gateway/DASHBOARD_ROADMAP.md)** — Implementation roadmap

## License

MarKom Gateway inherits LiteLLM's Apache 2.0 license. See the root `LICENSE` file.
