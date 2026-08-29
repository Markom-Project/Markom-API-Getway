# MarKom Gateway — Sub-Processor List

This document lists every third-party service that MarKom Gateway may call during operation. Clients can use this as their sub-processor list for compliance reviews (DPDPA, GDPR, etc.).

## Active Sub-Processors

| Service | Purpose | Data Transferred | Region Control | Required? |
|---------|---------|-----------------|----------------|-----------|
| **OpenAI API** | LLM inference (GPT-4o, GPT-4o-mini, GPT-5) | Prompts, completions | API region (configurable via `OPENAI_BASE_URL`) | Yes, if using OpenAI models |
| **Anthropic API** | LLM inference (Claude Sonnet 4, Claude 3.5 Haiku) | Prompts, completions | US (api.anthropic.com) | Yes, if using Anthropic models |
| **Embedding Provider** (OpenAI or self-hosted) | Semantic cache vector embeddings | Prompt text (no response) | Depends on `MARKOM_EMBEDDING_MODEL` config | Only if semantic cache enabled |
| **Pinecone** (optional) | Vector storage for semantic cache | Embedding vectors (no raw text) | Configurable by index region | Only if `MARKOM_CACHE_BACKEND=pinecone` |

## Local / Self-Hosted Components

These components run entirely within the client's deployment boundary. No data leaves the infrastructure:

| Component | Purpose | Data Stored |
|-----------|---------|-------------|
| **PostgreSQL** (NeonDB or local) | Audit trail, RBAC, accounts, role templates | Audit records, user data, role configs |
| **Redis** | Health metrics, cache TTL tracking | Request metrics, cache keys |
| **FAISS** (default) or Pinecone | Semantic cache index | Embedding vectors |
| **LiteLLM Proxy** | Request routing, key management | Request metadata (no prompt/response by default) |
| **MarKom Admin Service** | Dashboard API, RBAC enforcement | User sessions, role assignments |
| **Prometheus** | Metrics collection | Aggregated metrics (no PII) |
| **Grafana** | Dashboard visualization | Reads from Prometheus only |

## Data Boundary Summary

**What stays local (never leaves your infrastructure):**
- Audit trail records (Postgres)
- User accounts and RBAC data (Postgres)
- Health metrics and scoring (Redis)
- Cache entries (FAISS or Pinecone — Pinecone stores only vectors, not raw text)
- Admin dashboard state
- All Prometheus/Grafana metrics

**What may leave your infrastructure (depends on model provider):**
- LLM prompts and completions (sent to configured model providers)
- Embedding vectors (sent to embedding provider, unless self-hosted)

**What never leaves:**
- Raw prompt/response content is stored locally only if `MARKOM_AUDIT_REDACT_CONTENT=false` (default: redacted)
- PII detection results are stored locally in the audit trail
- All RBAC decisions are made locally

## Configuration for Data Residency

To ensure maximum data residency control:

1. **Audit content redaction**: Set `MARKOM_AUDIT_REDACT_CONTENT=true` to never store raw prompts/responses locally (only metadata)
2. **Embedding provider**: Use a self-hosted embedding model to keep all data local
3. **Cache backend**: Use FAISS (local) instead of Pinecone to keep vectors on-premises
4. **Model providers**: Use `OPENAI_BASE_URL` to route through a private endpoint or proxy

## Changes to Sub-Processor List

This list should be updated whenever:
- A new external service integration is added
- A model provider is configured
- The embedding provider is changed
- Pinecone is enabled/disabled

Last updated: 2026-08-29
