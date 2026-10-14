# Home PC deploy (Cloudflare Tunnel)

The public site (`https://scot-land.scot` / `https://www.scot-land.scot`) runs on
the office PC via Docker Compose and a **Cloudflare Tunnel** (`cloudflared`).
This is the live origin — not Vercel/Railway.

| Piece | Path / command |
|-------|----------------|
| Live stack | `docker-compose.home.yml` (ports `3000` frontend, `8000` API, `5433` PostGIS) |
| Canary stack | `docker-compose.home.canary.yml` (ports `3001` / `8001`) |
| Safe deploy | `scripts/ops/deploy-home.ps1` |
| Legacy name | `scripts/ops/rebuild-home.ps1` → calls deploy-home |
| Last good SHA | `.deploy/last-good-sha` (gitignored machine state) |
| Deploy log | `.deploy/deploy.log` |
| Uptime log | `.deploy/uptime.log` |

## Why this exists

A naive `docker compose up -d --build` rebuilds while tearing down containers.
Long frontend image builds leave the origin dead; Cloudflare then returns
**530 / Error 1033** (tunnel up, origin gone). Safe deploy **builds first**,
keeps the old stack and **never stops `cloudflared`**, health-checks a canary,
then swaps.

## Safe deploy sequence

Run on the home PC from the repo root (PowerShell):

```powershell
.\scripts\ops\deploy-home.ps1 -Pull
# or the old name:
.\scripts\ops\rebuild-home.ps1 -Pull
```

1. Confirm `cloudflared` policy: **never stop the tunnel**.
2. Optional `git pull origin main`.
3. Ensure live **db** is up (API/frontend keep serving the previous images).
4. `docker compose -f docker-compose.home.yml build` — new `scot-land-home-*:local` images; live containers untouched.
5. Start canary project `scot-land-canary` on `:8001` / `:3001` (shares live DB via `host.docker.internal:5433`).
6. Require canary `http://127.0.0.1:8001/health` **and** `http://127.0.0.1:3001/backend/health`.
7. Only then `docker compose … up -d --no-build` to swap live to the new images.
8. Require live `http://127.0.0.1:3000/backend/health`.
9. Tear down canary; write `.deploy/last-good-sha`.

### On failure

- Stop **canary only**.
- Check out the SHA in `.deploy/last-good-sha` and log the rollback to
  `.deploy/deploy.log`.
- If the live stack was **not** swapped yet (canary failed): leave live containers
  running; only reset git to last-good.
- If live **was** swapped and then failed health: rebuild last-good images and
  `up -d --no-build` to restore.
- **Do not** stop or restart `cloudflared`.

If there is no last-good file yet and canary fails before any swap, live stays on
the previous containers and the script exits non-zero.

## Auto-deploy hook

Point the existing home scheduled task / watcher at:

```powershell
cd C:\path\to\scot-land
.\scripts\ops\deploy-home.ps1 -Pull
```

Do **not** call raw `docker compose up -d --build` for production deploys.

## Uptime check ($0/month)

Probe the public path every **5 minutes** and log failures locally. No paid
uptime vendor.

**Windows (home PC) — Task Scheduler:**

```powershell
.\scripts\ops\register-uptime-task.ps1
# manual one-shot:
.\scripts\ops\uptime-check.ps1
```

**Linux cron:**

```cron
*/5 * * * * /path/to/scot-land/scripts/ops/uptime-check.sh
```

**systemd user timer** (copy/adapt unit paths in `scripts/ops/scot-land-uptime.service`):

```bash
mkdir -p ~/.config/systemd/user
cp scripts/ops/scot-land-uptime.service scripts/ops/scot-land-uptime.timer ~/.config/systemd/user/
# edit WorkingDirectory / ExecStart to the real clone path
systemctl --user daemon-reload
systemctl --user enable --now scot-land-uptime.timer
```

Default URL: `https://scot-land.scot/backend/health`. Override with
`SCOT_LAND_HEALTH_URL` (bash) or `-HealthUrl` (PowerShell). Failures append to
`.deploy/uptime.log`.

## Post-deploy smoke

After a successful safe deploy, still run the mandatory smoke when practical:

```powershell
.\scripts\smoke.ps1 -BaseUrl https://scot-land.scot
```

See `docs/OPERATING.md`.

## Operator notes

- Needs `.env` with `POSTGRES_PASSWORD` (same as today).
- Tunnel config stays outside this repo; deploy scripts must not `Stop-Process`
  / `systemctl stop` cloudflared.
- Canary ports must stay loopback-only so they are not public while testing.
