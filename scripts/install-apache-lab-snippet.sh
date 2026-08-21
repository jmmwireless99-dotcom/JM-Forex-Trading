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
        # Already inside vhost — ensure ProxyPass exclusion + API proxy
        changed = False
        if "ProxyPass /lab !" not in text and "ProxyPass /lab/ !" not in text:
            text = text.replace(
                "ProxyPass / http://127.0.0.1:8081/",
                "    ProxyPass /lab/ !\n    ProxyPass /lab !\n    ProxyPass / http://127.0.0.1:8081/",
                1,
            )
            changed = True
        elif "ProxyPass /lab/ !" not in text and "ProxyPass /lab !" in text:
            text = text.replace(
                "ProxyPass /lab !",
                "ProxyPass /lab/ !\n    ProxyPass /lab !",
                1,
            )
            changed = True
        dir_old = """    <Directory /opt/jm-lab/dist>
        Options -Indexes +FollowSymLinks
        AllowOverride None
        Require all granted
        FallbackResource /index.html
    </Directory>"""
        dir_mid = """    <Directory /opt/jm-lab/dist>
        Options -Indexes +FollowSymLinks
        AllowOverride None
        Require all granted
        RewriteEngine On
        RewriteCond %{REQUEST_FILENAME} !-f
        RewriteCond %{REQUEST_FILENAME} !-d
        RewriteRule ^ index.html [L]
        FallbackResource /index.html
    </Directory>"""
        dir_new = """    <Directory /opt/jm-lab/dist>
        Options -Indexes +FollowSymLinks
        AllowOverride None
        Require all granted
        RewriteEngine On
        RewriteCond %{REQUEST_URI} ^/lab/assets/ [NC]
        RewriteRule ^ - [L]
        RewriteCond %{REQUEST_FILENAME} !-f
        RewriteCond %{REQUEST_FILENAME} !-d
        RewriteRule ^ index.html [L]
        <Files "index.html">
            Header set Cache-Control "no-cache, no-store, must-revalidate"
        </Files>
    </Directory>"""
        if dir_old in text:
            text = text.replace(dir_old, dir_new)
            changed = True
        elif dir_mid in text:
            text = text.replace(dir_mid, dir_new)
            changed = True
        elif "RewriteCond %{REQUEST_URI} ^/lab/assets/" not in text and "Alias /lab /opt/jm-lab/dist" in text:
            # Upgrade any Directory block missing assets guard
            import re
            pat = re.compile(
                r"(    <Directory /opt/jm-lab/dist>\n.*?</Directory>)",
                re.DOTALL,
            )
            m = pat.search(text)
            if m and "RewriteCond %{REQUEST_URI} ^/lab/assets/" not in m.group(1):
                text = text[: m.start(1)] + dir_new + text[m.end(1) :]
                changed = True
        # Remove legacy broken vhost-level pair rewrite if present
        text = text.replace(
            "    RewriteCond %{REQUEST_URI} ^/lab/(EURUSD|GBPUSD|AUDNZD|EURCHF)/?$ [NC]\n    RewriteRule ^ /lab/index.html [L]\n",
            "",
        )
        if "ProxyPass /lab/api/" not in text:
            api_block = (
                "    # JM Lab demo trading API → port 8001 (isolated from JM FX /fx/)\n"
                "    ProxyPass /lab/api/ http://127.0.0.1:8001/api/\n"
                "    ProxyPassReverse /lab/api/ http://127.0.0.1:8001/api/\n\n"
            )
            text = text.replace("    # JM Lab static /lab/", api_block + "    # JM Lab static /lab/", 1)
            if "ProxyPass /lab/api/" not in text:
                text = text.replace("    Alias /lab /opt/jm-lab/dist", api_block + "    Alias /lab /opt/jm-lab/dist", 1)
            changed = True
        if changed:
            path.write_text(text)
            print("Updated Lab Apache rules (API proxy + /lab exclusion)")
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
