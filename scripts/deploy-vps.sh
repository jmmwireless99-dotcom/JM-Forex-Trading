#!/usr/bin/env bash
# Deploy JM Forex to the VPS that hosts jmtechsolution.cloud
# Usage (on the VPS):
#   cd /opt/jm-forex-trading && git pull && ./scripts/deploy-vps.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker not found. Install Docker first, then re-run."
  exit 1
fi

echo "[1/3] Building JM Forex image..."
docker compose build

echo "[2/3] Starting container on :8000..."
docker compose up -d

echo "[3/3] Health check..."
sleep 2
curl -fsS http://127.0.0.1:8000/api/health || {
  echo "Health check failed — see: docker compose logs -f"
  exit 1
}

echo
echo "JM Forex is running on http://127.0.0.1:8000"
echo "Next: point Apache forex.jmtechsolution.cloud → 127.0.0.1:8000"
echo "  sudo cp deploy/apache-forex.jmtechsolution.cloud.conf /etc/apache2/sites-available/forex.jmtechsolution.cloud.conf"
echo "  sudo a2enmod proxy proxy_http proxy_wstunnel headers rewrite ssl"
echo "  sudo a2ensite forex.jmtechsolution.cloud.conf"
echo "  sudo certbot --apache -d forex.jmtechsolution.cloud"
echo "  sudo systemctl reload apache2"
