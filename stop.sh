#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────
# MarKom Gateway — Stop All Services
# ─────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Stopping all MarKom Gateway services..."
docker compose --profile core --profile postgres --profile redis --profile monitoring down
echo "All services stopped."
