# MarKom Gateway

Production layer on top of LiteLLM — rebranded, with semantic caching, health-based routing, RBAC governance, and DPDPA-compliant audit trail.

## Architecture

```
markom_gateway/
├── proxy_config.yaml          # LiteLLM config: models, guardrails, callbacks
├── hooks/
│   ├── semantic_cache.py      # Vector similarity caching (FAISS + sentence-transformers)
│   ├── health_router.py       # Dynamic health-based provider routing (Redis)
│   ├── audit_logger.py        # Structured audit trail (Postgres)
│   └── pii_guardrail.py       # PII detection and redaction
├── admin_service/
│   ├── main.py                # FastAPI admin service with RBAC
│   └── markom_admin/
│       ├── rbac.py            # Role-based access control (Postgres)
│       └── ui/                # Admin dashboard shell (placeholder)
├── Dockerfile                 # Container build for admin service
├── requirements.txt           # Python dependencies
└── README.md                  # This file
```

## Quick Start

### Docker Compose (recommended)

```bash
# Set environment variables
export MARKOM_MASTER_KEY=sk-your-secret-key
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...

# Start all services
docker compose up -d

# Services:
#   LiteLLM proxy:    http://localhost:4000
#   Admin service:    http://localhost:8000
#   Postgres:         localhost:5433
#   Redis:            localhost:6379
#   Prometheus:       http://localhost:9090
```

### Local Development

```bash
# Install dependencies
pip install -r markom_gateway/requirements.txt
pip install litellm[proxy]

# Start LiteLLM with MarKom config
litellm --config markom_gateway/proxy_config.yaml --port 4000

# Start admin service (separate terminal)
uvicorn markom_gateway.admin_service.main:app --port 8000
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MARKOM_MASTER_KEY` | `sk-markom-secret` | Master key for admin access |
| `MARKOM_REDIS_URL` | `redis://localhost:6379` | Redis URL for health metrics |
| `MARKOM_AUDIT_DB_URL` | (uses `DATABASE_URL`) | Postgres URL for audit records |
| `MARKOM_ADMIN_DB_URL` | (uses `DATABASE_URL`) | Postgres URL for RBAC tables |
| `MARKOM_CACHE_SIMILARITY_THRESHOLD` | `0.95` | Minimum similarity for cache hit |
| `MARKOM_CACHE_TTL` | `3600` | Cache entry TTL in seconds |
| `MARKOM_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model for semantic cache |
| `MARKOM_AUDIT_REDACT_CONTENT` | `false` | Redact prompt/response in audit logs |
| `LITELLM_PROXY_URL` | `http://localhost:4000` | LiteLLM proxy URL (admin service) |

## Features

### Semantic Caching (Section 2)

Caches near-duplicate prompts using vector similarity search (FAISS). On cache hit, returns the cached response without calling the LLM.

- Configurable similarity threshold (default: 0.95)
- Per-model enable/disable via `MARKOM_CACHE_SKIP_MODELS`
- Manual purge endpoint: `POST /api/cache/purge`

### Health-Based Routing (Section 4)

Records per-provider latency, error rate, and timeout rate in Redis. Rewrites routing decisions to prefer the healthiest provider.

- Rolling 5-minute scoring window
- 1-2% exploration factor for score freshness
- Configurable scoring weights

### Compliance Audit Trail (Section 5)

Every request produces an immutable JSON record with: timestamp, user/team, model, tokens, cost, latency, guardrail results, routing decision.

- Append-only Postgres table
- Configurable retention period
- Content redaction support
- CSV/JSON export via admin API

### RBAC Governance (Section 3)

Four roles: `admin`, `team_lead`, `developer`, `viewer`. Enforced at the admin service layer.

- Role assignments stored in Postgres (`markom_roles`)
- All admin actions proxied to LiteLLM's management API
- Audit trail access restricted to `admin` role

### PII Guardrail (Section 6)

Optional PII detection and redaction in prompts. Supports custom regex patterns.

- Default patterns: email, phone, SSN, credit card, IP, Aadhaar, PAN
- Can block requests on PII detection (`block_on_detection=true`)

## Admin API Endpoints

| Method | Endpoint | Permission | Description |
|--------|----------|------------|-------------|
| `GET` | `/api/roles/list` | `manage_roles` | List users and roles |
| `POST` | `/api/roles/assign` | `manage_roles` | Assign a role |
| `DELETE` | `/api/roles/remove` | `manage_roles` | Remove a role |
| `GET` | `/api/roles/check` | auth | Check permission |
| `GET` | `/api/audit/records` | `view_audit` | Query audit records |
| `GET` | `/api/audit/stats` | `view_audit` | Audit statistics |
| `GET` | `/api/audit/export` | `export_audit` | Export CSV/JSON |
| `POST` | `/api/audit/purge` | `export_audit` | Purge old records |
| `POST` | `/api/cache/purge` | `manage_roles` | Purge semantic cache |
| `POST` | `/api/keys/generate` | `create_key` | Generate API key |
| `GET` | `/api/keys` | `view_key` | List API keys |
| `POST` | `/api/teams/new` | `create_team` | Create team |
| `GET` | `/api/teams` | `view_team` | List teams |

## UI Rebranding

The admin dashboard UI has been rebranded:
- Product name: "MarKom Gateway"
- Brand color: `#120505` (applied to CSS variables, Ant Design tokens, and component overrides)
- Dark theme with deep maroon accents

## Upgrading LiteLLM

The `markom_gateway/` directory is additive — no LiteLLM core files are modified. To upgrade:

1. Update the `litellm` version in `pyproject.toml` or `requirements.txt`
2. Rebuild the Docker images
3. Our hooks continue to work via the `CustomGuardrail` and `CustomLogger` plugin APIs

## License

MarKom Gateway inherits LiteLLM's Apache 2.0 license. See the root `LICENSE` file.
