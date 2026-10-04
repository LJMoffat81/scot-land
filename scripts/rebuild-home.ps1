$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:GIT_COMMIT = (git rev-parse HEAD)
docker compose -f docker-compose.home.yml up -d --build
