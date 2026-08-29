#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────
# MarKom Gateway — Run Script
# Starts all services for local development
# ─────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; }

# ── Check Docker ────────────────────────────────────────────

if ! command -v docker &> /dev/null; then
    error "Docker not installed. Install it from https://docs.docker.com/get-docker/"
    exit 1
fi

if ! docker info &> /dev/null 2>&1; then
    warn "Docker daemon not running or no permission. Trying with sudo..."
    if ! sudo docker info &> /dev/null 2>&1; then
        error "Cannot connect to Docker. Start Docker Desktop or run: sudo systemctl start docker"
        exit 1
    fi
    DOCKER="sudo docker"
    COMPOSE="sudo docker compose"
else
    DOCKER="docker"
    COMPOSE="docker compose"
fi

# ── Check .env ──────────────────────────────────────────────

if [ ! -f .env ]; then
    error ".env file not found."
    echo "  Create one with at minimum:"
    echo '    GOOGLE_API_KEY=your-key'
    echo '    MARKOM_MASTER_KEY=sk-markom-secret-key-change-me'
    exit 1
fi

# Load .env
set -a
source .env
set +a

# Check required keys
if [ -z "${GOOGLE_API_KEY:-}" ]; then
    warn "GOOGLE_API_KEY not set — semantic cache embeddings will fail"
fi
if [ -z "${MARKOM_MASTER_KEY:-}" ]; then
    error "MARKOM_MASTER_KEY not set — cannot start"
    exit 1
fi

# ── Start Infrastructure ────────────────────────────────────

echo ""
echo "─── MarKom Gateway — Starting ─────────────────────────"
echo ""

# Postgres
info "Starting Postgres..."
$COMPOSE --profile postgres up -d db

# Redis
info "Starting Redis..."
$COMPOSE --profile redis up -d redis

# Wait for Postgres to be healthy
echo -n "  Waiting for Postgres"
for i in $(seq 1 30); do
    if $COMPOSE exec -T db pg_isready -d litellm -U llmproxy &> /dev/null 2>&1; then
        echo ""
        info "Postgres ready"
        break
    fi
    echo -n "."
    sleep 1
done

# Wait for Redis to be healthy
echo -n "  Waiting for Redis"
for i in $(seq 1 15); do
    if $COMPOSE exec -T redis redis-cli ping &> /dev/null 2>&1; then
        echo ""
        info "Redis ready"
        break
    fi
    echo -n "."
    sleep 1
done

# ── Start Core Services ─────────────────────────────────────

echo ""
info "Building and starting LiteLLM + Admin service..."
$COMPOSE --profile core up -d --build

# Wait for LiteLLM to be healthy
echo -n "  Waiting for LiteLLM"
for i in $(seq 1 40); do
    if curl -s http://localhost:4000/health/liveliness &> /dev/null 2>&1; then
        echo ""
        info "LiteLLM ready"
        break
    fi
    echo -n "."
    sleep 2
done

# Wait for Admin service to be healthy
echo -n "  Waiting for Admin service"
for i in $(seq 1 20); do
    if curl -s http://localhost:8000/health &> /dev/null 2>&1; then
        echo ""
        info "Admin service ready"
        break
    fi
    echo -n "."
    sleep 2
done

# ── Start Monitoring (optional) ─────────────────────────────

if [ "${MARKOM_PROMETHEUS_ENABLED:-false}" = "true" ] || [ "${MARKOM_GRAFANA_ENABLED:-false}" = "true" ]; then
    echo ""
    info "Starting monitoring..."
    $COMPOSE --profile monitoring up -d
fi

# ── Done ────────────────────────────────────────────────────

echo ""
echo "─── MarKom Gateway — Running ──────────────────────────"
echo ""
echo "  Dashboard:     http://localhost:8000/dashboard"
echo "  Login key:     ${MARKOM_MASTER_KEY}"
echo ""
echo "  LiteLLM:       http://localhost:4000"
echo "  Postgres:      localhost:5433"
echo "  Redis:         localhost:6379"
echo ""

if [ "${MARKOM_PROMETHEUS_ENABLED:-false}" = "true" ]; then
    echo "  Prometheus:    http://localhost:${PROMETHEUS_PORT:-9090}"
fi
if [ "${MARKOM_GRAFANA_ENABLED:-false}" = "true" ]; then
    echo "  Grafana:       http://localhost:${GRAFANA_PORT:-3000}  (admin/admin)"
fi

echo ""
echo "  Stop:          ./stop.sh"
echo "  Logs:          $COMPOSE logs -f"
echo "────────────────────────────────────────────────────────"
echo ""
