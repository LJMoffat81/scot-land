# Free / self-hosted uptime probe for the public home origin.
# Hits https://scot-land.scot/backend/health every run; logs failures (and
# optionally successes) under .deploy/uptime.log. No paid uptime vendor.
#
# Schedule every 5 minutes — see docs/HOME_DEPLOY.md:
#   .\scripts\ops\register-uptime-task.ps1
# Or Windows Task Scheduler / cron calling this script.

[CmdletBinding()]
param(
    [string]$HealthUrl = "https://scot-land.scot/backend/health",
    [int]$TimeoutSec = 30,
    [switch]$LogSuccess
)

$ErrorActionPreference = "Continue"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$DeployDir = Join-Path $RepoRoot ".deploy"
$LogFile = Join-Path $DeployDir "uptime.log"

if (-not (Test-Path $DeployDir)) {
    New-Item -ItemType Directory -Path $DeployDir | Out-Null
}

function Write-UptimeLog([string]$Message, [string]$Level = "INFO") {
    $line = "{0:yyyy-MM-dd HH:mm:ss} [{1}] {2}" -f (Get-Date), $Level, $Message
    Add-Content -Path $LogFile -Value $line
    if ($Level -eq "ERROR" -or $Level -eq "WARN") {
        Write-Host $line
    }
}

try {
    $resp = Invoke-WebRequest -Uri $HealthUrl -Method GET -TimeoutSec $TimeoutSec -UseBasicParsing
    $code = [int]$resp.StatusCode
    if ($code -eq 200) {
        if ($LogSuccess) {
            Write-UptimeLog "OK $HealthUrl HTTP $code"
        }
        exit 0
    }
    Write-UptimeLog "FAIL $HealthUrl HTTP $code" "ERROR"
    exit 1
} catch {
    Write-UptimeLog "FAIL $HealthUrl $($_.Exception.Message)" "ERROR"
    exit 1
}
