# Scot-LAND — one-time deploy helper
# Requires: Node.js, Railway account, Vercel account

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "=== Scot-LAND deploy ===" -ForegroundColor Cyan
Write-Host ""

Write-Host "Step 1: Railway (API)" -ForegroundColor Yellow
Write-Host "  1. Go to https://railway.app → New Project → Deploy from GitHub"
Write-Host "  2. Select scotland-open-land (uses railway.toml)"
Write-Host "  3. Set variables: ALLOWED_ORIGINS, ALLOW_VERCEL_PREVIEWS=true"
Write-Host "  4. Copy the public URL"
Write-Host ""
Write-Host "  Or via CLI:"
Write-Host "    npx @railway/cli login"
Write-Host "    cd $RepoRoot"
Write-Host "    npx @railway/cli up"
Write-Host ""

$railwayUrl = Read-Host "Paste Railway API URL (or Enter to skip)"
if ($railwayUrl) {
    Write-Host "Testing $railwayUrl/health ..."
    try {
        $health = Invoke-RestMethod -Uri "$railwayUrl/health" -TimeoutSec 15
        Write-Host "  OK: version $($health.version), signoff $($health.economist_signoff_status)" -ForegroundColor Green
    } catch {
        Write-Host "  API not reachable yet — deploy Railway first." -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Step 2: Vercel (frontend)" -ForegroundColor Yellow
Write-Host "  1. Go to https://vercel.com → Import scotland-open-land"
Write-Host "  2. Root Directory: frontend"
Write-Host "  3. Env: NEXT_PUBLIC_API_URL = your Railway URL"
Write-Host ""
Write-Host "  Or via CLI:"
Write-Host "    npx vercel login"
Write-Host "    cd $RepoRoot\frontend"
if ($railwayUrl) {
    Write-Host "    `$env:NEXT_PUBLIC_API_URL='$railwayUrl'; npx vercel --prod"
} else {
    Write-Host "    `$env:NEXT_PUBLIC_API_URL='https://YOUR-RAILWAY-URL'; npx vercel --prod"
}

Write-Host ""
Write-Host "Step 3: Link CORS" -ForegroundColor Yellow
Write-Host "  Add your Vercel URL to Railway ALLOWED_ORIGINS and redeploy API."
Write-Host ""
Write-Host "Done. Map live at your Vercel URL." -ForegroundColor Green