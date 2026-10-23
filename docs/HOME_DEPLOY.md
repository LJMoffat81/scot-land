# Home PC deploy (Cloudflare Tunnel)

The public site (`https://scot-land.scot` / `https://www.scot-land.scot`) runs on
the office PC via Docker Compose and a **Cloudflare Tunnel** (`cloudflared`).
This is the live origin — not Vercel/Railway.

| Piece | Path / command |
|-------|----------------|
| Live stack | `docker-compose.home.yml` (loopback `3000` frontend, `8000` API, `5433` PostGIS) |
| Canary stack | `docker-compose.home.canary.yml` (ports `3001` / `8001`) |
| Tunnel template | `deploy/cloudflare/config.template.yml` |
| Offline Worker | `deploy/cloudflare/worker-offline/` |
| Access template | `deploy/cloudflare/access.template.yml` |
| Safe deploy | `scripts/ops/deploy-home.ps1` |
| Daily pg_dump | `scripts/ops/pg-dump-daily.ps1` (keep 14) |
| Legacy name | `scripts/ops/rebuild-home.ps1` → calls deploy-home |
| Last good SHA | `.deploy/last-good-sha` (gitignored machine state) |
| Last good images | `scot-land-home-api:last-good`, `scot-land-home-frontend:last-good` |
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

`Invoke-Compose` in `deploy-home.ps1` takes one explicit `-ComposeArgs` string
array (for example `@('-f', $ComposePath, 'up', '-d', '--no-recreate', 'db')`).
Do not pass bare remaining arguments: PowerShell would bind `-d` / `-p` / `-f` to
common parameters and the compose step can hang attached. Do not move `HEAD` by
hand before running the script — `last-good-sha` records `HEAD` before the pull.
All docker/git calls go through `Invoke-Native`, which judges success only by exit code, so stderr progress text
under PowerShell 5.1 never aborts a deploy. `last-good-sha` is written only after live health passes (or recorded
before a pull when HEAD already equals it / none exists); rollback never writes it. If a pull changes
`deploy-home.ps1`, the script stops with exit 3 and asks you to re-run the same command.

1. Confirm `cloudflared` policy: **never stop the tunnel**.
2. Optional `-Pull`: **before** `git pull`, record current `HEAD` as
   `.deploy/last-good-sha` and tag current `:local` images as `:last-good`
   only when last-good is missing or already equals that `HEAD` (otherwise keep
   the confirmed SHA and do not re-snapshot images).
3. Optional `git pull origin main` (only after step 2). If the pull changes
   `deploy-home.ps1`, exit 3 and re-run the same command (nothing built yet).
4. Ensure live **db** is up (API/frontend keep serving the previous images).
5. Snapshot `:local` → `:last-good` when last-good is known and `-Pull` was not
   used (so a build cannot erase the restore tags).
6. `docker compose -f docker-compose.home.yml build api frontend` — new
   `scot-land-home-*:local` images; live containers untouched. Never a bare
   full-project `build` / `up` that recreates every service.
7. Start canary project `scot-land-canary` on `:8001` / `:3001` (shares live DB via `host.docker.internal:5433`).
8. Require canary `http://127.0.0.1:8001/health` **and** `http://127.0.0.1:3001/backend/health`.
9. Only then `docker compose … up -d --no-build --no-deps api frontend` to swap
   the app services. **Never** recreate `cloudflared` (not in this compose;
   stay out of its process/service too).
10. Require live `http://127.0.0.1:3000/backend/health`.
11. Write `.deploy/last-good-sha`; retag new `:local` as `:last-good`; then tear
    down canary (best-effort — teardown failure must not roll back a healthy deploy).

### On failure

- Stop **canary only**.
- Check out **`main`**, then `git reset --hard` to the SHA in
  `.deploy/last-good-sha` (never a detached checkout of the SHA alone).
- Retag `scot-land-home-*:last-good` → `scot-land-home-*:local`.
- If the live stack was **not** swapped yet (canary failed): leave live containers
  running; git + image tags are restored for the next attempt.
- If live **was** swapped and then failed health:
  `up -d --no-build --no-deps api frontend` using the retagged `:local` images
  (no rebuild; no full-stack recreate).
- Log the rollback to `.deploy/deploy.log`.
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

## Named tunnel (HOME-TUNNEL)

Repo template: `deploy/cloudflare/config.template.yml` (placeholders only — no
secrets). Copy it onto the home PC and replace `REPLACE_WITH_TUNNEL_ID` and
`REPLACE_WITH_CREDENTIALS_FILE`.

Ingress is intentionally minimal:

1. `scot-land.scot` → `http://localhost:3000`
2. `www.scot-land.scot` → `http://localhost:3000`
3. `http_status:404` catch-all **last**

There is **no** `/api` → `:8000` rule. The API container serves at its root
(`/health`, …); the front end already proxies public API traffic at
`/backend/*`. Postgres (`5432` / published `5433`) is never in the ingress.

Live compose binds the front end to loopback only
(`127.0.0.1:${HOME_FRONTEND_PORT:-3000}:3000`), matching API and db. The
tunnel reaches the stack via `cloudflared` on the PC — not via router port
forwards.

### cloudflared as a Windows service (no router ports)

1. Install [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
   on the home PC.
2. Place the filled config (from the template) outside the git working tree,
   e.g. `%USERPROFILE%\.cloudflared\config.yml`, with the credentials JSON
   beside it.
3. Install and start the Windows service (elevated PowerShell), pointing at
   that config — for example:

   ```powershell
   cloudflared service install
   # If the service needs an explicit config path, set it per Cloudflare's
   # current Windows service docs for your cloudflared build.
   Start-Service cloudflared
   ```

4. Do **not** open inbound router ports (no WAN NAT to 3000 / 8000 / 5433).
   Only Cloudflare → `cloudflared` → loopback reaches the stack.
5. Deploy scripts must never stop this service (see safe deploy above).

### Offline Worker

Template: `deploy/cloudflare/worker-offline/`. When the tunnel or origin is
down, the Worker returns plain text:

`Scot-LAND is offline for a short while. Please try again later.`

Deploy with Wrangler from a local copy of `wrangler.toml.template` (fill
account/zone placeholders; never commit tokens).

### Cloudflare Access (admin / docs-admin)

Template: `deploy/cloudflare/access.template.yml`. Protect `/admin` and
`/docs-admin` (and subpaths) on both hostnames. Public map and `/backend`
stay open. Identity rules stay in the Cloudflare account — not in git.

### Cache headers

- Static assets (`/_next/static`, mark image, swagger-ui) and map tiles: long
  `Cache-Control` lifetimes.
- GET `/backend/*` responses: `public, max-age=300` (5 minutes) unless the
  upstream already sent `no-store` / `private`, or a longer `max-age` (kept,
  with `ETag`). The tunnel template does not rewrite these headers.

### ARCH-2a tiles (PMTiles → `/v1/tiles` MVT)

Host directory (gitignored machine state; default sibling of the repo):

```powershell
$env:SCOT_LAND_TILES_DIR = "C:\path\to\scot-land-tiles"   # or ../scot-land-tiles
New-Item -ItemType Directory -Force -Path $env:SCOT_LAND_TILES_DIR | Out-Null
```

Build all registry tilesets (one-off container, tiles volume read-write):

```powershell
docker compose -f docker-compose.home.yml run --rm --no-deps `
  -v "${env:SCOT_LAND_TILES_DIR}:/app/tiles" `
  -e TILES_DIR=/app/tiles `
  api python -m tiles.build --all
```

The live/canary `api` services mount the same path read-only as `/app/tiles`
with `TILES_DIR=/app/tiles`. Clients use:

- `GET /v1/tiles/manifest.json` (short cache)
- `GET /v1/tiles/{id}/{version}/{z}/{x}/{y}.mvt` (immutable)
- `GET /v1/tiles/{id}/{version}/values/{measure}.json` (immutable; pop_density / simd_decile only)

After deploying ARCH-2b, run `tiles.build --all` once so the manifest gains
`title`, `geometry`, `style`, `legend`, `measure`, and `source_layer` from the
registry. Old PMTiles files stay valid; only the manifest keys are new.

**Cloudflare Cache Rule (free plan, dashboard — not in this repo):** Cloudflare
does not cache `.mvt` / `.json` by default. Add one Cache Rule before 2b goes
live:

- When: `hostname eq scot-land.scot` and
  `starts_with(http.request.uri.path, "/backend/v1/tiles/")`
- Then: *Eligible for cache*, edge TTL **use origin Cache-Control**

No paid Cloudflare feature is required. Until the rule exists, tiles are
fetched from origin with the correct `Cache-Control` / `ETag` headers.

## Daily PostGIS backup (14 copies)

```powershell
.\scripts\ops\pg-dump-daily.ps1
.\scripts\ops\register-pg-dump-task.ps1
```

- Writes dated `scot-land-YYYY-MM-DD.dump` under `.deploy/pg-dumps/` (gitignored).
- Keeps the newest **14** dumps; older files are deleted.
- Task Scheduler: daily (default 02:30). See comments in
  `register-pg-dump-task.ps1`. Needs `pg_dump` on PATH and
  `POSTGRES_PASSWORD` / `PGPASSWORD` available to the task account — never
  commit secrets.

## Operator notes

- Needs `.env` with `POSTGRES_PASSWORD` (same as today).
- Tunnel config stays outside this repo; deploy scripts must not `Stop-Process`
  / `systemctl stop` cloudflared.
- Canary ports must stay loopback-only so they are not public while testing.
- No router port forwards; named tunnel + Windows `cloudflared` service only.
