# Scot-LAND — safe home auto-deploy (Cloudflare Tunnel origin).
#
# Build new images first while the live stack keeps serving. Start a canary on
# :8001/:3001, require /backend/health, then swap live. On failure: roll back to
# the last good commit, log it, and never stop cloudflared.
#
# Usage (from repo root, on the home PC):
#   .\scripts\ops\deploy-home.ps1
#   .\scripts\ops\deploy-home.ps1 -Pull
#   .\scripts\ops\rebuild-home.ps1   # thin wrapper → this script
#
# State (gitignored): .deploy/last-good-sha, .deploy/deploy.log

[CmdletBinding()]
param(
    [switch]$Pull,
    [int]$HealthTimeoutSec = 180,
    [string]$ComposeFile = "docker-compose.home.yml",
    [string]$CanaryComposeFile = "docker-compose.home.canary.yml",
    [string]$CanaryProject = "scot-land-canary",
    [string]$HealthPath = "/backend/health",
    [string]$CanaryFrontendUrl = "http://127.0.0.1:3001",
    [string]$LiveFrontendUrl = "http://127.0.0.1:3000",
    [string]$CanaryApiUrl = "http://127.0.0.1:8001",
    [string]$LiveApiUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $RepoRoot

$DeployDir = Join-Path $RepoRoot ".deploy"
$LogFile = Join-Path $DeployDir "deploy.log"
$LastGoodFile = Join-Path $DeployDir "last-good-sha"
$ComposePath = Join-Path $RepoRoot $ComposeFile
$CanaryPath = Join-Path $RepoRoot $CanaryComposeFile

function Write-DeployLog {
    param([string]$Message, [string]$Level = "INFO")
    $line = "{0:yyyy-MM-dd HH:mm:ss} [{1}] {2}" -f (Get-Date), $Level, $Message
    Write-Host $line
    if (-not (Test-Path $DeployDir)) {
        New-Item -ItemType Directory -Path $DeployDir | Out-Null
    }
    Add-Content -Path $LogFile -Value $line
}

function Get-CloudflaredRunning {
    $proc = Get-Process -Name "cloudflared" -ErrorAction SilentlyContinue
    if ($proc) { return $true }
    try {
        $svc = Get-Service -Name "cloudflared" -ErrorAction SilentlyContinue
        if ($svc -and $svc.Status -eq "Running") { return $true }
    } catch { }
    return $false
}

function Assert-CloudflaredUntouched {
    # Hard rule: this script must never stop the tunnel. Call sites only log.
    Write-DeployLog "cloudflared policy: never stop the tunnel (running=$(Get-CloudflaredRunning))"
}

function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$ComposeArgs)
    & docker compose @ComposeArgs
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose $($ComposeArgs -join ' ') failed with exit $LASTEXITCODE"
    }
}

function Test-HttpOk {
    param([string]$Url, [int]$TimeoutSec = 5)
    try {
        $resp = Invoke-WebRequest -Uri $Url -Method GET -TimeoutSec $TimeoutSec -UseBasicParsing
        return ([int]$resp.StatusCode -eq 200)
    } catch {
        return $false
    }
}

function Wait-HttpOk {
    param(
        [string]$Url,
        [int]$TimeoutSec = 180,
        [string]$Label = "health"
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    Write-DeployLog "Waiting for $Label at $Url (timeout ${TimeoutSec}s)"
    while ((Get-Date) -lt $deadline) {
        if (Test-HttpOk -Url $Url) {
            Write-DeployLog "$Label OK: $Url"
            return $true
        }
        Start-Sleep -Seconds 3
    }
    Write-DeployLog "$Label FAILED after ${TimeoutSec}s: $Url" "ERROR"
    return $false
}

function Read-LastGoodSha {
    if (Test-Path $LastGoodFile) {
        return (Get-Content -Path $LastGoodFile -Raw).Trim()
    }
    return ""
}

function Write-LastGoodSha {
    param([string]$Sha)
    if (-not (Test-Path $DeployDir)) {
        New-Item -ItemType Directory -Path $DeployDir | Out-Null
    }
    Set-Content -Path $LastGoodFile -Value $Sha.Trim() -NoNewline
    Write-DeployLog "Recorded last-good SHA: $Sha"
}

function Stop-Canary {
    Write-DeployLog "Stopping canary project $CanaryProject (live + tunnel untouched)"
    & docker compose -p $CanaryProject -f $CanaryPath down --remove-orphans 2>$null
}

function Invoke-GitLastGood {
    param([string]$LastGood)
    Write-DeployLog "Checking out last-good commit $LastGood"
    & git checkout --force $LastGood
    if ($LASTEXITCODE -ne 0) {
        Write-DeployLog "git checkout $LastGood failed" "ERROR"
        return $false
    }
    $env:GIT_COMMIT = $LastGood
    return $true
}

function Invoke-Rollback {
    param(
        [string]$Reason,
        # When $false, live was never swapped — only drop canary + reset git.
        [bool]$RestackLive = $true
    )
    $lastGood = Read-LastGoodSha
    Write-DeployLog "ROLLBACK: $Reason (restack_live=$RestackLive)" "ERROR"
    Stop-Canary
    Assert-CloudflaredUntouched

    if (-not $lastGood) {
        Write-DeployLog "No last-good SHA on disk; leaving live stack as-is (images not swapped or still previous)." "ERROR"
        return $false
    }

    if (-not (Invoke-GitLastGood -LastGood $lastGood)) {
        Assert-CloudflaredUntouched
        return $false
    }

    if (-not $RestackLive) {
        Write-DeployLog "Live stack was not swapped; left running. Git reset to $lastGood. Tunnel untouched."
        Assert-CloudflaredUntouched
        return $true
    }

    try {
        Invoke-Compose -f $ComposePath build
        Invoke-Compose -f $ComposePath up -d --no-build
        $ok = Wait-HttpOk -Url "$LiveFrontendUrl$HealthPath" -TimeoutSec $HealthTimeoutSec -Label "live $HealthPath after rollback"
        Assert-CloudflaredUntouched
        if ($ok) {
            Write-DeployLog "Rollback restored live stack at $lastGood"
        } else {
            Write-DeployLog "Rollback completed git+compose but health still failing — tunnel left running" "ERROR"
        }
        return $ok
    } catch {
        Write-DeployLog "Rollback error: $_" "ERROR"
        Assert-CloudflaredUntouched
        return $false
    }
}

# --- main --------------------------------------------------------------------

if (-not (Test-Path $ComposePath)) { throw "Missing $ComposePath" }
if (-not (Test-Path $CanaryPath)) { throw "Missing $CanaryPath" }

Assert-CloudflaredUntouched
if (-not (Get-CloudflaredRunning)) {
    Write-DeployLog "WARNING: cloudflared not detected as a process/service. Continuing deploy; will still never stop it." "WARN"
}

if ($Pull) {
    Write-DeployLog "git pull origin main"
    & git pull origin main
    if ($LASTEXITCODE -ne 0) { throw "git pull failed" }
}

$targetSha = (& git rev-parse HEAD).Trim()
$env:GIT_COMMIT = $targetSha
Write-DeployLog "Deploy target SHA: $targetSha"

# Seed last-good from a healthy live stack when the file is missing.
$existingGood = Read-LastGoodSha
if (-not $existingGood) {
    if (Test-HttpOk -Url "$LiveFrontendUrl$HealthPath") {
        Write-LastGoodSha $targetSha
        Write-DeployLog "Seeded last-good from currently healthy live stack at $targetSha"
    }
}

try {
    Write-DeployLog "Ensuring live db is up (old api/frontend keep serving)"
    Invoke-Compose -f $ComposePath up -d db

    Write-DeployLog "Building new images (live containers keep running)"
    Invoke-Compose -f $ComposePath build

    Write-DeployLog "Starting canary on alternate ports (live + tunnel keep running)"
    Invoke-Compose -p $CanaryProject -f $CanaryPath up -d --no-build

    $canaryApiOk = Wait-HttpOk -Url "$CanaryApiUrl/health" -TimeoutSec $HealthTimeoutSec -Label "canary API /health"
    $canaryFeOk = $false
    if ($canaryApiOk) {
        $canaryFeOk = Wait-HttpOk -Url "$CanaryFrontendUrl$HealthPath" -TimeoutSec $HealthTimeoutSec -Label "canary $HealthPath"
    }

    if (-not ($canaryApiOk -and $canaryFeOk)) {
        Invoke-Rollback -Reason "canary health failed for $targetSha" -RestackLive $false | Out-Null
        Assert-CloudflaredUntouched
        exit 1
    }

    Write-DeployLog "Canary healthy — swapping live stack to new images"
    Invoke-Compose -f $ComposePath up -d --no-build

    $liveOk = Wait-HttpOk -Url "$LiveFrontendUrl$HealthPath" -TimeoutSec $HealthTimeoutSec -Label "live $HealthPath"
    if (-not $liveOk) {
        Invoke-Rollback -Reason "live health failed after swap for $targetSha" -RestackLive $true | Out-Null
        Assert-CloudflaredUntouched
        exit 1
    }

    Stop-Canary
    Write-LastGoodSha $targetSha
    Assert-CloudflaredUntouched
    Write-DeployLog "Deploy SUCCESS at $targetSha"
    exit 0
} catch {
    Write-DeployLog "Deploy exception: $_" "ERROR"
    Invoke-Rollback -Reason "exception during deploy of $targetSha : $_" | Out-Null
    Assert-CloudflaredUntouched
    exit 1
}
