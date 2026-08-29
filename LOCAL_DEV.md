# Local Development & Testing Guide

Everything you need to run MarKom Gateway on your laptop for development and testing.

---

## Prerequisites

| Tool | Version | Why |
|------|---------|-----|
| Docker + Docker Compose | v2.20+ | Runs Postgres, Redis, LiteLLM, admin service |
| Python | 3.11+ | For local (non-Docker) development |
| Git | any | Clone the repo |
| At least one LLM API key | — | OpenAI or Anthropic (for real requests) |

---

## Quick Start (Docker — recommended)

```bash
# 1. Clone
git clone https://github.com/arpanchakraborty23/Markom-API-Getway.git
cd Markom-API-Getway

# 2. Edit .env — set at minimum:
#    OPENAI_API_KEY=sk-...
#    MARKOM_MASTER_KEY=sk-markom-secret-key-change-me

# 3. Start everything
./start.sh

# 4. Open
#    Dashboard:  http://localhost:8000/dashboard
#    LiteLLM:    http://localhost:4000
#    Grafana:    http://localhost:3000  (admin/admin)
```

## Quick Start (Local Python — no Docker)

```bash
# 1. Start only Postgres and Redis
docker compose --profile postgres --profile redis up -d

# 2. Install dependencies
python -m venv .venv && source .venv/bin/activate
pip install litellm[proxy]
pip install -r markom_gateway/requirements.txt

# 3. Start LiteLLM (terminal 1)
litellm --config markom_gateway/proxy_config.yaml --port 4000

# 4. Start admin service (terminal 2)
#    Update MARKOM_LITELLM_URL in .env to http://localhost:4000 first
uvicorn markom_gateway.admin_service.main:app --port 8000 --reload

# 5. Open http://localhost:8000/dashboard
```

---

## .env Reference — Every Variable Explained

### LLM Provider API Keys

At least one is required to make real LLM requests. Without them, the proxy starts but all requests fail.

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `OPENAI_API_KEY` | Yes* | `""` | API key for OpenAI models (GPT-4o, GPT-5). Get from platform.openai.com |
| `OPENAI_BASE_URL` | No | `""` | Override OpenAI API base URL (for Azure, proxies, or local models) |
| `ANTHROPIC_API_KEY` | No | `""` | API key for Anthropic models (Claude). Get from console.anthropic.com |
| `COHERE_API_KEY` | No | `""` | API key for Cohere models |
| `AZURE_API_BASE` | No | `""` | Azure OpenAI endpoint URL |
| `AZURE_API_VERSION` | No | `""` | Azure OpenAI API version (e.g. `2024-02-15-preview`) |
| `AZURE_API_KEY` | No | `""` | Azure OpenAI API key |
| `REPLICATE_API_KEY` | No | `""` | API key for Replicate models |
| `NOVITA_API_KEY` | No | `""` | API key for Novita models |
| `INFINITY_API_KEY` | No | `""` | API key for Infinity endpoint |

*At least `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` must be set for the proxy to serve requests.

### OpenRouter (optional)

| Variable | Default | Purpose |
|----------|---------|---------|
| `OR_SITE_URL` | `""` | Your site URL for OpenRouter attribution |
| `OR_APP_NAME` | `"MarKom Gateway"` | App name shown in OpenRouter dashboard |
| `OR_API_KEY` | `""` | OpenRouter API key (routes through openrouter.ai) |

### Core Settings

| Variable | Default | Purpose |
|----------|---------|---------|
| `MARKOM_MASTER_KEY` | `sk-markom-secret-key-change-me` | **Change this in production!** Master key for admin access. Used by both the admin service and LiteLLM proxy. Keep this secret. |

### Database

| Variable | Default | Purpose |
|----------|---------|---------|
| `MARKOM_DATABASE_URL` | `postgresql://llmproxy:dbpassword9090@db:5432/litellm` | Single Postgres URL for everything — LiteLLM model/key storage, audit trail tables, RBAC tables. For NeonDB, replace with your NeonDB connection string. |
| `STORE_MODEL_IN_DB` | `"True"` | LiteLLM setting: store model configs in Postgres instead of just the YAML file. |

**One URL for everything.** If you need separate databases for audit trail or RBAC in production, you can set `MARKOM_AUDIT_DB_URL` or `MARKOM_ADMIN_DB_URL` as overrides (falls back to `MARKOM_DATABASE_URL`).

### Redis

| Variable | Default | Purpose |
|----------|---------|---------|
| `MARKOM_REDIS_ENABLED` | `"true"` | `"true"` = run local Redis container. `"false"` = health router uses in-memory fallback (less accurate). |
| `MARKOM_REDIS_URL` | `redis://redis:6379` | Redis connection string. For local Docker, use `redis://redis:6379`. For local Python, use `redis://localhost:6379`. |

### Semantic Cache

| Variable | Default | Purpose |
|----------|---------|---------|
| `MARKOM_CACHE_BACKEND` | `"faiss"` | `"faiss"` = local vector search (no external service). `"pinecone"` = cloud vector DB (requires Pinecone key). |
| `MARKOM_EMBEDDING_MODEL` | `"text-embedding-3-small"` | OpenAI embedding model for converting prompts to vectors. Requires `OPENAI_API_KEY`. |
| `MARKOM_CACHE_SIMILARITY_THRESHOLD` | `"0.95"` | Minimum cosine similarity (0.0–1.0) to consider two prompts a "match". Higher = stricter, fewer cache hits. |
| `MARKOM_CACHE_TTL` | `"3600"` | How long (seconds) a cache entry lives before expiring. 3600 = 1 hour. |
| `MARKOM_CACHE_MAX_ENTRIES` | `"10000"` | Maximum cache entries before oldest are evicted. |
| `MARKOM_CACHE_SKIP_MODELS` | `""` | Comma-separated model names to never cache (e.g. `"gpt-5,claude-sonnet-4-20250514"`). Use for time-sensitive or streaming models. |

**Local dev tip:** FAISS works entirely locally — no API calls, no cost. Set threshold to `0.80` during testing to get more cache hits.

### Health Router

| Variable | Default | Purpose |
|----------|---------|---------|
| `MARKOM_SCORING_WINDOW` | `"300"` | Rolling window (seconds) for calculating provider health scores. 300 = 5 minutes. |
| `MARKOM_EXPLORATION_RATE` | `"0.02"` | Percentage (0.0–1.0) of requests randomly routed to lower-scored providers. Keeps scores fresh. 0.02 = 2%. |
| `MARKOM_LATENCY_WEIGHT` | `"0.4"` | Weight of latency in health score calculation. Should sum to 1.0 with error and timeout weights. |
| `MARKOM_ERROR_WEIGHT` | `"0.4"` | Weight of error rate in health score calculation. |
| `MARKOM_TIMEOUT_WEIGHT` | `"0.2"` | Weight of timeout rate in health score calculation. |

### Audit Trail (DPDPA Compliance)

| Variable | Default | Purpose |
|----------|---------|---------|
| `MARKOM_AUDIT_REDACT_CONTENT` | `"false"` | `"true"` = never store raw prompt/response text. Only metadata (model, cost, latency, tokens) is kept. Safest for compliance. |
| `MARKOM_AUDIT_RAW_CONTENT_TEAMS` | `""` | Comma-separated team IDs allowed to store raw prompts. Only works when `REDACT_CONTENT=false`. Example: `"team-alpha,team-beta"`. |
| `MARKOM_AUDIT_RETENTION_DAYS` | `"90"` | Days to keep audit metadata (timestamps, costs, tokens). After this, records are deleted. |
| `MARKOM_PROMPT_RETENTION_DAYS` | `"30"` | Days to keep raw prompt/response text (if stored). Shorter than metadata retention — content is redacted after this period. |
| `MARKOM_CACHE_RETENTION_DAYS` | `"30"` | Days to keep cache entries. |

**Local dev tip:** Set `REDACT_CONTENT=true` during testing if you don't want prompt text in your local DB.

### PII Guardrail

| Variable | Default | Purpose |
|----------|---------|---------|
| `MARKOM_PII_ENABLED` | `"false"` | `"true"` = scan prompts for PII (email, phone, SSN, credit card, Aadhaar, PAN). |
| `MARKOM_PII_BLOCK_ON_DETECTION` | `"false"` | `"true"` = block the request entirely when PII is found. `"false"` = log the detection but let the request through. |

**Local dev tip:** Leave disabled unless testing PII detection specifically.

### Pinecone (future upgrade)

| Variable | Default | Purpose |
|----------|---------|---------|
| `PINECONE_API_KEY` | `""` | Pinecone API key. Only needed when `CACHE_BACKEND=pinecone`. |
| `PINECONE_INDEX_NAME` | `""` | Pinecone index name. |
| `PINECONE_NAMESPACE` | `"markom-cache"` | Pinecone namespace for cache entries. |

### Admin Service

| Variable | Default | Purpose |
|----------|---------|---------|
| `MARKOM_LITELLM_URL` | `"http://litellm:4000"` | URL the admin service uses to call LiteLLM's management API. Use `http://localhost:4000` for local Python dev. |
| `MARKOM_ADMIN_PORT` | `"8000"` | Port for the admin dashboard API. |

### Monitoring

| Variable | Default | Purpose |
|----------|---------|---------|
| `MARKOM_PROMETHEUS_ENABLED` | `"true"` | `"true"` = run Prometheus container. |
| `PROMETHEUS_HOST` | `"0.0.0.0"` | Prometheus bind address. |
| `PROMETHEUS_PORT` | `"9090"` | Prometheus UI port. |
| `MARKOM_GRAFANA_ENABLED` | `"true"` | `"true"` = run Grafana container (auto-connects to Prometheus). |
| `GRAFANA_HOST` | `"0.0.0.0"` | Grafana bind address. |
| `GRAFANA_PORT` | `"3000"` | Grafana UI port. |
| `GRAFANA_ADMIN_USER` | `"admin"` | Grafana admin username. |
| `GRAFANA_ADMIN_PASSWORD` | `"admin"` | Grafana admin password. **Change in production!** |
| `GRAFANA_ALLOW_SIGN_UP` | `"false"` | Allow new user sign-ups in Grafana. |

---

## Minimum .env for Local Testing

```bash
# Required: at least one LLM key
OPENAI_API_KEY=sk-your-key-here

# Required: admin access
MARKOM_MASTER_KEY=sk-markom-secret-key-change-me

# Database (local Docker Postgres)
MARKOM_DATABASE_URL=postgresql://llmproxy:dbpassword9090@db:5432/litellm

# Redis (local Docker Redis)
MARKOM_REDIS_ENABLED=true
MARKOM_REDIS_URL=redis://redis:6379

# Cache (local FAISS, no external service needed)
MARKOM_CACHE_BACKEND=faiss
MARKOM_EMBEDDING_MODEL=text-embedding-3-small
MARKOM_CACHE_SIMILARITY_THRESHOLD=0.90

# Audit (safe defaults for dev)
MARKOM_AUDIT_REDACT_CONTENT=false
MARKOM_AUDIT_RETENTION_DAYS=90
MARKOM_PROMPT_RETENTION_DAYS=30

# Admin service (connects to local LiteLLM)
MARKOM_LITELLM_URL=http://litellm:4000

# Monitoring (optional, disable to save resources)
MARKOM_PROMETHEUS_ENABLED=false
MARKOM_GRAFANA_ENABLED=false
```

---

## Testing the API

### 1. Send a chat completion

```bash
curl http://localhost:4000/chat/completions \
  -H "Authorization: Bearer sk-markom-secret-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hello, world!"}]
  }'
```

### 2. Send with purpose metadata (for audit trail)

```bash
curl http://localhost:4000/chat/completions \
  -H "Authorization: Bearer sk-markom-secret-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Summarize this document"}],
    "metadata": {
      "purpose_team": "engineering",
      "purpose_feature": "document-summarizer",
      "purpose_use_case": "internal-docs",
      "data_principal_id": "user-12345"
    }
  }'
```

### 3. Check audit trail

```bash
curl http://localhost:8000/api/audit/records \
  -H "Authorization: Bearer sk-markom-secret-key-change-me"
```

### 4. Export data for a data principal (DPDPA)

```bash
curl -X POST http://localhost:8000/api/compliance/principal/export \
  -H "Authorization: Bearer sk-markom-secret-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"data_principal_id": "user-12345"}'
```

### 5. Test semantic cache (send same prompt twice)

```bash
# First call — cache miss, hits LLM
curl http://localhost:4000/chat/completions \
  -H "Authorization: Bearer sk-markom-secret-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"What is 2+2?"}]}'

# Second call — cache hit, returns instantly
curl http://localhost:4000/chat/completions \
  -H "Authorization: Bearer sk-markom-secret-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"What is 2+2?"}]}'
```

---

## Accessing the Dashboard

1. Open `http://localhost:8000/dashboard` in your browser
2. Sign in with the master key: `sk-markom-secret-key-change-me`
3. You'll see the admin dashboard with tabs based on your role (admin = all tabs)

### Testing Different Roles

```bash
# Create a test user with viewer role (sees only Home tab)
curl -X POST http://localhost:8000/api/accounts \
  -H "Authorization: Bearer sk-markom-secret-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"external_id":"test-viewer","role":"viewer","email":"viewer@test.com","display_name":"Test Viewer"}'

# Create an API key for that user (use it to log in as viewer)
# Then sign in at /dashboard with that key to see limited tabs
```

---

## Common Issues

| Problem | Fix |
|---------|-----|
| `No module named 'markom_gateway'` | Run from repo root, or set `PYTHONPATH=.` |
| `Connection refused` on port 5433 | Postgres not started — run `docker compose --profile postgres up -d` |
| `Connection refused` on port 6379 | Redis not started — run `docker compose --profile redis up -d` |
| `Invalid API key` on dashboard | The key must match `MARKOM_MASTER_KEY` or be a user's API key in `markom_users` table |
| Semantic cache not working | Check `OPENAI_API_KEY` is set (embedding model needs it) |
| Audit records empty | Check `MARKOM_DATABASE_URL` is set and Postgres is running |
| Health scores not updating | Check `MARKOM_REDIS_URL` is correct and Redis is running |

---

## Stopping Services

```bash
# Stop everything
./stop.sh

# Or manually stop specific profiles
docker compose --profile core --profile postgres down
```
