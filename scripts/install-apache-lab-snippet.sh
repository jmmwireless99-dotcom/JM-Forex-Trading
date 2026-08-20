#!/usr/bin/env bash
# One-time: add JM Lab Apache snippet to the JM TECH SSL vhost (safe — does not edit /fx/ rules).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SNIP="$ROOT/deploy/apache-lab-path.conf"
MARKER="# JM Lab static /lab/"

if [[ ! -f "$SNIP" ]]; then
  echo "Missing $SNIP"
  exit 1
fi

# Find vhost that already serves /fx/
VHOST=""
for f in /etc/apache2/sites-enabled/*.conf; do
  [[ -f "$f" ]] || continue
  if grep -q '/fx/' "$f" 2>/dev/null; then
    VHOST="$f"
    break
  fi
done

if [[ -z "$VHOST" ]]; then
  echo "Could not find Apache vhost with /fx/ — add manually:"
  echo "  Include contents of $SNIP"
  exit 1
fi

if grep -q "$MARKER" "$VHOST" 2>/dev/null; then
  echo "Already installed in $VHOST"
else
  echo "Installing lab snippet into $VHOST"
  sudo cp -a "$VHOST" "${VHOST}.bak-jm-lab-$(date +%Y%m%d)"
  {
    echo ""
    echo "$MARKER"
    cat "$SNIP"
  } | sudo tee -a "$VHOST" >/dev/null
fi

sudo apache2ctl configtest
sudo systemctl reload apache2
echo "Apache reloaded — /lab/ should be live after deploy-lab-portal.sh"
