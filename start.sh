#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────
# MarKom Gateway — Startup Script
# Selectively starts services based on .env toggles
# ─────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env
if [ -f .env ]; then
    set -a
    source .env
    set +a
else
    echo "ERROR: .env file not found. Copy .env.example to .env first."
    exit 1
fi

# Build profiles list
PROFILES="core"

# Postgres
if [ "${MARKOM_POSTGRES_ENABLED:-true}" = "true" ]; then
    PROFILES="$PROFILES,postgres"
    echo "  [x] Postgres"
else
    echo "  [ ] Postgres (disabled — using external DB)"
fi

# Redis
if [ "${MARKOM_REDIS_ENABLED:-true}" = "true" ]; then
    PROFILES="$PROFILES,redis"
    echo "  [x] Redis"
else
    echo "  [ ] Redis (disabled — in-memory fallback)"
fi

# Monitoring (Prometheus + Grafana)
if [ "${MARKOM_PROMETHEUS_ENABLED:-true}" = "true" ] || [ "${MARKOM_GRAFANA_ENABLED:-true}" = "true" ]; then
    PROFILES="$PROFILES,monitoring"
    if [ "${MARKOM_PROMETHEUS_ENABLED:-true}" = "true" ]; then
        echo "  [x] Prometheus (port ${PROMETHEUS_PORT:-9090})"
    else
        echo "  [ ] Prometheus (disabled)"
    fi
    if [ "${MARKOM_GRAFANA_ENABLED:-true}" = "true" ]; then
        echo "  [x] Grafana (port ${GRAFANA_PORT:-3000})"
    else
        echo "  [ ] Grafana (disabled)"
    fi
fi

echo ""
echo "Active profiles: $PROFILES"
echo ""

# Run docker compose with selected profiles
docker compose --profile "${PROFILES//,/,}" up -d --build

echo ""
echo "─── MarKom Gateway ────────────────────────────────────"
echo "  LiteLLM Proxy:    http://localhost:4000"
echo "  Admin Service:    http://localhost:8000"
if [ "${MARKOM_PROMETHEUS_ENABLED:-true}" = "true" ]; then
    echo "  Prometheus:       http://localhost:${PROMETHEUS_PORT:-9090}"
fi
if [ "${MARKOM_GRAFANA_ENABLED:-true}" = "true" ]; then
    echo "  Grafana:          http://localhost:${GRAFANA_PORT:-3000}"
fi
echo "───────────────────────────────────────────────────────"
