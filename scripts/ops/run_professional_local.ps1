# Local professional stack: API + notes for frontend
# Usage: from repo root  .\scripts\run_professional_local.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not (Test-Path "$Root\backend")) {
  $Root = Split-Path -Parent $MyInvocation.MyCommand.Path
  $Root = Split-Path -Parent $Root
}

Write-Host "Scot-LAND - professional local checks" -ForegroundColor Cyan
Write-Host "Repo: $Root"

Set-Location "$Root\backend"
if (-not (Test-Path .\.venv\Scripts\Activate.ps1)) {
  python -m venv .venv
}
.\.venv\Scripts\Activate.ps1
pip install -q -r requirements.txt pytest

Write-Host "`n== pytest ==" -ForegroundColor Yellow
python -m pytest tests/ -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n== sales fixture ingest ==" -ForegroundColor Yellow
python -m etl.ingest_sales --path ..\data\fixtures\sales\ward18_synthetic.jsonl

Write-Host "`n== mini-roll (Edinburgh + Glasgow points) ==" -ForegroundColor Yellow
python -m etl.batch_assess `
  --lat 55.9533 --lng -3.1883 `
  --lat 55.8642 --lng -4.2518 `
  --out ..\data\processed\demo_roll.jsonl `
  --format jsonl

Write-Host "`nOK. Start API:  cd backend; uvicorn api.main:app --reload --app-dir ." -ForegroundColor Green
Write-Host "Start UI:   cd frontend; npm run dev" -ForegroundColor Green
Write-Host "Reports:    GET /assessment/report  |  QA: GET /validation/ward18-qa-pack" -ForegroundColor Green
