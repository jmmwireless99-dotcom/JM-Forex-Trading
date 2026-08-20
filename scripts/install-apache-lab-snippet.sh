#!/usr/bin/env bash
# One-time: add JM Lab Apache rules INSIDE the SSL vhost (before catch-all ProxyPass /).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SNIP="$ROOT/deploy/apache-lab-path.conf"
MARKER="# JM Lab static /lab/"

if [[ ! -f "$SNIP" ]]; then
  echo "Missing $SNIP"
  exit 1
fi

VHOST=""
for f in /etc/apache2/sites-enabled/*.conf; do
  [[ -f "$f" ]] || continue
  if grep -q '/fx/' "$f" 2>/dev/null; then
    VHOST="$f"
    break
  fi
done

if [[ -z "$VHOST" ]]; then
  echo "Could not find Apache vhost with /fx/"
  exit 1
fi

sudo cp -a "$VHOST" "${VHOST}.bak-jm-lab-$(date +%Y%m%d%H%M)"

python3 << PY
from pathlib import Path
path = Path("${VHOST}")
text = path.read_text()
marker = "${MARKER}"

# Remove old snippet appended outside VirtualHost (legacy bug)
if marker in text:
    idx = text.index(marker)
    # If marker is after </VirtualHost>, strip trailing orphan block
    vh_end = text.rfind("</VirtualHost>", 0, idx)
    if vh_end != -1:
        text = text[: vh_end + len("</VirtualHost>")] + "\n"
    elif "Alias /lab /opt/jm-lab/dist" in text:
        # Already inside vhost — ensure ProxyPass exclusion
        if "ProxyPass /lab !" not in text:
            text = text.replace(
                "ProxyPass / http://127.0.0.1:8081/",
                "ProxyPass /lab !\n    ProxyPass / http://127.0.0.1:8081/",
                1,
            )
            path.write_text(text)
            print("Added ProxyPass /lab ! exclusion")
        else:
            print("Lab Apache rules already present in ${VHOST}")
        raise SystemExit(0)

snippet = Path("${SNIP}").read_text()
# Insert before JM TECH catch-all proxy (8081 portal)
anchors = [
    "    # JM TECH SOLUTION portal + API + phone pay (:8081, BASE_PATH empty)",
    "    ProxyPass / http://127.0.0.1:8081/",
]
inserted = False
for anchor in anchors:
    if anchor in text and "Alias /lab /opt/jm-lab/dist" not in text.split(anchor)[0]:
        text = text.replace(anchor, snippet + "\n" + anchor, 1)
        inserted = True
        break
if not inserted:
    raise SystemExit("Could not find insertion point in ${VHOST}")

path.write_text(text)
print("Installed JM Lab snippet inside ${VHOST}")
PY

sudo apache2ctl configtest
sudo systemctl reload apache2
echo "Apache reloaded — /lab/ ready after deploy-lab-portal.sh"
