# Deploy JM Forex on jmtechsolution.cloud VPS

Goal:

- Desk URL: **https://forex.jmtechsolution.cloud**
- Portal button on **https://jmtechsolution.cloud** → opens Forex Trading

Your VPS already serves JM TECH SOLUTION (Apache + Express on Ubuntu @ `72.62.73.235`).

> Important: this deploys the **web AI desk + paper engine**.  
> MT4 EA still needs a **Windows** machine/VPS for real demo order execution.

---

## A) DNS (ikaw — domain panel)

Add an **A record**:

| Type | Name | Value |
| --- | --- | --- |
| A | `forex` | `72.62.73.235` |

Result: `forex.jmtechsolution.cloud` → same VPS.

---

## B) Upload & run on VPS (SSH)

```bash
# SSH into VPS
ssh user@72.62.73.235

# Clone / pull
sudo mkdir -p /opt
sudo git clone https://github.com/jmmwireless99-dotcom/JM-Forex-Trading.git /opt/jm-forex-trading
# or: cd /opt/jm-forex-trading && git pull

cd /opt/jm-forex-trading
git checkout cursor/jm-forex-platform-automation-26e2   # or main after merge

# Install Docker if needed, then:
chmod +x scripts/deploy-vps.sh
./scripts/deploy-vps.sh
```

App listens on `127.0.0.1:8000`.

---

## C) Apache reverse proxy + SSL

```bash
sudo a2enmod proxy proxy_http proxy_wstunnel headers rewrite ssl
sudo cp /opt/jm-forex-trading/deploy/apache-forex.jmtechsolution.cloud.conf \
  /etc/apache2/sites-available/forex.jmtechsolution.cloud.conf
sudo a2ensite forex.jmtechsolution.cloud.conf
sudo certbot --apache -d forex.jmtechsolution.cloud
sudo systemctl reload apache2
```

Test:

```bash
curl -I https://forex.jmtechsolution.cloud
curl https://forex.jmtechsolution.cloud/api/health
```

---

## D) Forex Trading button sa JM TECH portal

Sa source ng `jmtechsolution.cloud` sidebar nav, idagdag:

```js
const FOREX_URL = "https://forex.jmtechsolution.cloud";

// inside .nav buttons:
html`<button type="button" onClick=${() => window.open(FOREX_URL, "_blank", "noopener,noreferrer")}>
  <span>FX</span> Forex Trading
</button>`
```

Snippet file: `deploy/portal-forex-button.snippet.js`

Kung wala akong access sa portal repo/SSH, **ikaw** mag-a-add ng button — o bigyan mo ako ng:

1. SSH user + key (o temporary password) sa VPS  
2. Path ng portal code (hal. `/var/www/jmtechsolution`)  
3. Go-signal i-edit ang sidebar

---

## E) MT4 later (separate)

| Layer | Where |
| --- | --- |
| Website desk + AI signals | Ubuntu VPS (`forex.jmtechsolution.cloud`) |
| MT4 order execution | Windows PC or Windows VPS + `JM_Forex_Bridge.mq4` |

---

## Need from you to finish upload for you

Reply with:

1. SSH login (example: `ssh root@72.62.73.235` or `ubuntu@...`)  
2. Confirmation DNS `forex` A record is set  
3. Portal source path on the server  

Then I can run the deploy commands directly (kung may SSH access).
