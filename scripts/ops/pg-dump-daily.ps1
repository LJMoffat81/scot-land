# Daily dated pg_dump of the home PostGIS database. Keeps the newest 14 copies.
# No secrets in this script - password comes from the environment / .env on the PC.
#
#   .\scripts\ops\pg-dump-daily.ps1
#   .\scripts\ops\pg-dump-daily.ps1 -Keep 14 -OutDir C:\Backups\scot-land-pg
#
# Schedule with register-pg-dump-task.ps1 (Task Scheduler notes in docs/HOME_DEPLOY.md).

[CmdletBinding()]
param(
    [string]$OutDir = "",
    [int]$Keep = 14,
    [string]$HostName = "127.0.0.1",
    [int]$Port = 5433,
    [string]$User = $(if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "scotland" }),
    [string]$Database = $(if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "scotland_wealth" }),
    [string]$PgDump = "pg_dump"
)

$ErrorActionPreference = "Stop"

if ($Keep -lt 1) {
    throw "Keep must be >= 1 (HOME-TUNNEL keeps 14 dated copies)."
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
if (-not $OutDir) {
    $OutDir = Join-Path $RepoRoot ".deploy\pg-dumps"
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$stamp = Get-Date -Format "yyyy-MM-dd"
$outFile = Join-Path $OutDir "scot-land-$stamp.dump"

# Prefer PGPASSWORD from the environment; never write it to disk or logs.
if (-not $env:PGPASSWORD -and (Test-Path (Join-Path $RepoRoot ".env"))) {
    Get-Content (Join-Path $RepoRoot ".env") | ForEach-Object {
        if ($_ -match '^\s*POSTGRES_PASSWORD=(.+)\s*$') {
            $env:PGPASSWORD = $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
}

Write-Host "pg_dump -> $outFile"
& $PgDump --host $HostName --port $Port --username $User --dbname $Database `
    --format=custom --file $outFile
if ($LASTEXITCODE -ne 0) {
    throw "pg_dump failed with exit $LASTEXITCODE"
}

$dumps = Get-ChildItem -Path $OutDir -Filter "scot-land-*.dump" |
    Sort-Object LastWriteTime -Descending
if ($dumps.Count -gt $Keep) {
    $dumps | Select-Object -Skip $Keep | ForEach-Object {
        Write-Host "Removing old dump $($_.Name)"
        Remove-Item -LiteralPath $_.FullName -Force
    }
}

Write-Host "Kept $([Math]::Min($dumps.Count, $Keep)) of max $Keep dumps in $OutDir"
