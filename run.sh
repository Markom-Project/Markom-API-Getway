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
    error "Docker not installed. Install from https://docs.docker.com/get-docker/"
    exit 1
fi

if ! docker info &> /dev/null 2>&1; then
    warn "Docker needs sudo. Trying..."
    if ! sudo docker info &> /dev/null 2>&1; then
        error "Cannot connect to Docker. Start Docker Desktop or: sudo systemctl start docker"
        exit 1
    fi
    COMPOSE="sudo docker compose"
else
    COMPOSE="docker compose"
fi

# ── Check .env ──────────────────────────────────────────────

if [ ! -f .env ]; then
    error ".env file not found."
    echo "  Create with:"
    echo '    GOOGLE_API_KEY=your-key'
    echo '    MARKOM_MASTER_KEY=sk-markom-secret-key-change-me'
    exit 1
fi

set -a
source .env
set +a

if [ -z "${MARKOM_MASTER_KEY:-}" ]; then
    error "MARKOM_MASTER_KEY not set in .env"
    exit 1
fi

# ── Stop any existing containers ────────────────────────────

echo ""
$COMPOSE down --remove-orphans 2>/dev/null || true

# ── Start Core Services ─────────────────────────────────────

echo ""
echo "─── MarKom Gateway — Starting ─────────────────────────"
echo ""

info "Building and starting LiteLLM + Admin service..."
$COMPOSE --profile core up -d --build

# Wait for LiteLLM
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

# Wait for Admin service
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
