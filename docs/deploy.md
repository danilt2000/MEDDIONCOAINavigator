# Server deployment

The demo runs on an Ubuntu 24.04 server behind Cloudflare, next to other sites:

| Address | What |
|---|---|
| https://pacient.nastasiya.com | patient PWA (`apps/patient-pwa/dist`) |
| https://lekar.nastasiya.com | clinician web (`apps/doctor-web/dist`) |
| `/api`, `/mock` on both | FastAPI on 127.0.0.1:8100 (systemd `meddi-api`) |
| 127.0.0.1:8101 | MCP server (systemd `meddi-mcp`) |
| 127.0.0.1:52773, :1972 | IRIS for Health (`docker compose`, container `meddi-iris`), reachable over an SSH tunnel only |

Host nginx terminates TLS with the Cloudflare origin certificate for `*.nastasiya.com` (`deploy/nginx/meddi.conf`).
Cloudflare DNS: proxied A records `pacient` and `lekar` pointing at the server.

## First install

```bash
git clone https://github.com/danilt2000/MEDDIONCOAINavigator.git /opt/meddi && cd /opt/meddi
# .env with OPENAI_API_KEY (copied from the developer machine, chmod 600)
chown -R 51773:51773 iris/inbox                      # irisowner in the container writes processed HL7 files there
docker compose up -d --build && sh iris/scripts/install.sh
python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt
bash scripts/seed.sh                                 # FHIR resources, MEDDI.* tables, Vector Search
docker run --rm -v /opt/meddi:/app -w /app node:22 bash -c "corepack enable && CI=1 pnpm install --frozen-lockfile && pnpm -r build"
cp deploy/systemd/*.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now meddi-api meddi-mcp
ufw allow from 172.16.0.0/12 to any port 8100 proto tcp   # IRIS alert operation -> API on the host
ln -s /opt/meddi/deploy/nginx/meddi.conf /etc/nginx/sites-enabled/meddi.conf && nginx -t && systemctl reload nginx
```

## Update

```bash
cd /opt/meddi && git pull
docker run --rm -v /opt/meddi:/app -w /app node:22 bash -c "corepack enable && CI=1 pnpm install --frozen-lockfile && pnpm -r build"
backend/.venv/bin/pip install -r backend/requirements.txt && systemctl restart meddi-api meddi-mcp
```

A restart of `meddi-api` resets the demo state (clock 9. 9. 2026 21:50, replayed history), like a local restart.

IRIS portal from a laptop: `ssh -L 52773:127.0.0.1:52773 root@<server>`, then http://localhost:52773/csp/sys/UtilHome.csp.
