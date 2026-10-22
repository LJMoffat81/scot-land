# Scot-LAND - safe home auto-deploy (Cloudflare Tunnel origin).
#
# Build new images first while the live stack keeps serving. Start a canary on
# :8001/:3001, require /backend/health, then swap live. On failure: roll back to
# the last good commit on branch main (not detached), retag last-good images to
# :local, log it, and never stop cloudflared.
#
# Usage (from repo root, on the home PC):
#   .\scripts\ops\deploy-home.ps1
#   .\scripts\ops\deploy-home.ps1 -Pull
#   .\scripts\ops\rebuild-home.ps1   # thin wrapper -> this script
#
# State (gitignored): .deploy/last-good-sha, .deploy/deploy.log
# Image tags: scot-land-home-{api,frontend}:local and :last-good

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
$ApiImageLocal = "scot-land-home-api:local"
$ApiImageLastGood = "scot-land-home-api:last-good"
$FrontendImageLocal = "scot-land-home-frontend:local"
$FrontendImageLastGood = "scot-land-home-frontend:last-good"

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

# Native docker/git: success is $LASTEXITCODE only (stderr must not abort under 5.1 Stop).
function Invoke-Native {
    param(
        [Parameter(Mandatory)][string]$Exe,
        [Parameter(Mandatory)][string[]]$ArgList,
        [switch]$AllowNonZero
    )
    $ErrorActionPreference = 'Continue'
    $out = & $Exe @ArgList 2>&1
    $code = $LASTEXITCODE
    $stdout = @($out | Where-Object { $_ -isnot [System.Management.Automation.ErrorRecord] } | ForEach-Object { "$_" })
    $stderr = @($out | Where-Object { $_ -is  [System.Management.Automation.ErrorRecord] } | ForEach-Object { "$_" })
    foreach ($l in $stdout + $stderr) { Write-Host $l }
    if ($code -ne 0 -and -not $AllowNonZero) {
        throw "native command failed: $Exe $($ArgList -join ' ') (exit $code)"
    }
    [pscustomobject]@{ ExitCode = $code; StdOut = ($stdout -join "`n"); StdErr = ($stderr -join "`n") }
}

# Pass compose argv as one explicit array via -ComposeArgs. Do not use
# ValueFromRemainingArguments: bare -d/-p/-f bind to common parameters and hang.
function Invoke-Compose {
    param([string[]]$ComposeArgs)
    Invoke-Native -Exe docker -ArgList (@('compose') + $ComposeArgs) | Out-Null
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

function Test-PrePullRecordAllowed {
    param([string]$Existing, [string]$Head)
    return (-not $Existing) -or ($Existing -eq $Head)
}

function Get-DeployScriptHash {
    param([Parameter(Mandatory)][string]$Path)
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash
}

function Test-DeployScriptChanged {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Before
    )
    $after = Get-DeployScriptHash -Path $Path
    return ($after -ne $Before)
}

function Test-DockerImageExists {
    param([string]$Image)
    return ((Invoke-Native -Exe docker -ArgList @('image', 'inspect', $Image) -AllowNonZero).ExitCode -eq 0)
}

function Save-LastGoodImages {
    # Snapshot :local -> :last-good before a build overwrites :local.
    $pairs = @(
        @{ Src = $ApiImageLocal; Dst = $ApiImageLastGood },
        @{ Src = $FrontendImageLocal; Dst = $FrontendImageLastGood }
    )
    foreach ($p in $pairs) {
        if (-not (Test-DockerImageExists -Image $p.Src)) {
            Write-DeployLog "No $($p.Src) to snapshot as $($p.Dst) (first deploy or missing image)" "WARN"
            continue
        }
        # docker tag (native via Invoke-Native)
        Invoke-Native -Exe docker -ArgList @('tag', $p.Src, $p.Dst) | Out-Null
        Write-DeployLog "Tagged $($p.Src) -> $($p.Dst)"
    }
}

function Restore-LastGoodImages {
    # Retag preserved last-good images back to :local for compose reuse.
    $pairs = @(
        @{ Src = $ApiImageLastGood; Dst = $ApiImageLocal },
        @{ Src = $FrontendImageLastGood; Dst = $FrontendImageLocal }
    )
    foreach ($p in $pairs) {
        if (-not (Test-DockerImageExists -Image $p.Src)) {
            Write-DeployLog "Missing $($p.Src); cannot retag to $($p.Dst)" "ERROR"
            return $false
        }
        # docker tag (native via Invoke-Native)
        $tagResult = Invoke-Native -Exe docker -ArgList @('tag', $p.Src, $p.Dst) -AllowNonZero
        if ($tagResult.ExitCode -ne 0) {
            Write-DeployLog "docker tag $($p.Src) $($p.Dst) failed with exit $($tagResult.ExitCode)" "ERROR"
            return $false
        }
        Write-DeployLog "Retagged $($p.Src) -> $($p.Dst)"
    }
    return $true
}

function Stop-Canary {
    Write-DeployLog "Stopping canary project $CanaryProject (live + tunnel untouched)"
    $down = Invoke-Native -Exe docker -ArgList @('compose', '-p', $CanaryProject, '-f', $CanaryPath, 'down', '--remove-orphans') -AllowNonZero
    if ($down.ExitCode -ne 0) {
        Write-DeployLog "canary teardown exit $($down.ExitCode)" "WARN"
    }
}

function Invoke-GitLastGood {
    param([string]$LastGood)
    # Stay on main: checkout the branch, then hard-reset to last-good (never detach).
    Write-DeployLog "Checking out main and resetting to last-good $LastGood (not detached)"
    # git checkout --force main
    $co = Invoke-Native -Exe git -ArgList @('checkout', '--force', 'main') -AllowNonZero
    if ($co.ExitCode -ne 0) {
        Write-DeployLog "git checkout main failed" "ERROR"
        return $false
    }
    # git reset --hard $LastGood
    $rs = Invoke-Native -Exe git -ArgList @('reset', '--hard', $LastGood) -AllowNonZero
    if ($rs.ExitCode -ne 0) {
        Write-DeployLog "git reset --hard $LastGood failed" "ERROR"
        return $false
    }
    $env:GIT_COMMIT = $LastGood
    return $true
}

function Invoke-Rollback {
    param(
        [string]$Reason,
        # When $false, live was never swapped - drop canary, reset main, retag images.
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

    if (-not (Restore-LastGoodImages)) {
        Write-DeployLog "Failed to retag last-good images to :local" "ERROR"
        Assert-CloudflaredUntouched
        return $false
    }

    if (-not $RestackLive) {
        Write-DeployLog "Live stack was not swapped; left running. main reset to $lastGood; :local retagged from :last-good. Tunnel untouched."
        Assert-CloudflaredUntouched
        return $true
    }

    try {
        # Images already retagged to :local - recreate app services only (never cloudflared/db).
        # Safety contract (static test): up -d --no-build --no-deps api frontend
        Invoke-Compose -ComposeArgs @('-f', $ComposePath, 'up', '-d', '--no-build', '--no-deps', 'api', 'frontend')
        $ok = Wait-HttpOk -Url "$LiveFrontendUrl$HealthPath" -TimeoutSec $HealthTimeoutSec -Label "live $HealthPath after rollback"
        Assert-CloudflaredUntouched
        if ($ok) {
            Write-DeployLog "Rollback restored live stack at $lastGood (retag :last-good -> :local)"
        } else {
            Write-DeployLog "Rollback completed git+retag+compose but health still failing - tunnel left running" "ERROR"
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

$scriptHashBefore = Get-DeployScriptHash $PSCommandPath

Assert-CloudflaredUntouched
if (-not (Get-CloudflaredRunning)) {
    Write-DeployLog "WARNING: cloudflared not detected as a process/service. Continuing deploy; will still never stop it." "WARN"
}

# Required before any pull: record HEAD as last-good and snapshot :local images.
$prePullSha = (Invoke-Native -Exe git -ArgList @('rev-parse', 'HEAD')).StdOut.Trim()
if ($Pull) {
    $existingPre = Read-LastGoodSha
    if (Test-PrePullRecordAllowed -Existing $existingPre -Head $prePullSha) {
        Write-DeployLog "Recording HEAD as last-good before pull: $prePullSha"
        Write-LastGoodSha $prePullSha
        Save-LastGoodImages
    } else {
        Write-DeployLog "Keeping last-good $existingPre; HEAD $prePullSha was never confirmed deployed (no overwrite, no image snapshot)" "WARN"
    }
    Write-DeployLog "git pull origin main"
    Invoke-Native -Exe git -ArgList @('pull', 'origin', 'main') | Out-Null
    if (Test-DeployScriptChanged -Path $PSCommandPath -Before $scriptHashBefore) {
        $msg = "DEPLOY-SCRIPT-CHANGED: git pull updated deploy-home.ps1. Re-run the same command to deploy with the new script."
        Write-DeployLog $msg "WARN"
        Write-Host $msg
        exit 3
    }
}

$targetSha = (Invoke-Native -Exe git -ArgList @('rev-parse', 'HEAD')).StdOut.Trim()
$env:GIT_COMMIT = $targetSha
Write-DeployLog "Deploy target SHA: $targetSha"

# Seed last-good when the file is still missing (no -Pull, or first run).
$existingGood = Read-LastGoodSha
if (-not $existingGood) {
    if (Test-HttpOk -Url "$LiveFrontendUrl$HealthPath") {
        Write-LastGoodSha $prePullSha
        Write-DeployLog "Seeded last-good from currently healthy live stack at $prePullSha"
    }
}

# Before build overwrites :local, snapshot current images when we have a last-good SHA
# and have not already snapshotted in the -Pull path above.
if ((Read-LastGoodSha) -and -not $Pull) {
    Save-LastGoodImages
}

try {
    Write-DeployLog "Ensuring live db is up (old api/frontend keep serving)"
    # Safety contract (static test): up -d --no-recreate db
    Invoke-Compose -ComposeArgs @('-f', $ComposePath, 'up', '-d', '--no-recreate', 'db')

    Write-DeployLog "Building new api/frontend images (live containers keep running; cloudflared untouched)"
    # Safety contract (static test): build api frontend
    Invoke-Compose -ComposeArgs @('-f', $ComposePath, 'build', 'api', 'frontend')

    Write-DeployLog "Starting canary on alternate ports (live + tunnel keep running)"
    Invoke-Compose -ComposeArgs @('-p', $CanaryProject, '-f', $CanaryPath, 'up', '-d', '--no-build')

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

    Write-DeployLog "Canary healthy - swapping live api/frontend only (no cloudflared, no bare full-stack up)"
    # Safety contract (static test): up -d --no-build --no-deps api frontend
    Invoke-Compose -ComposeArgs @('-f', $ComposePath, 'up', '-d', '--no-build', '--no-deps', 'api', 'frontend')

    $liveOk = Wait-HttpOk -Url "$LiveFrontendUrl$HealthPath" -TimeoutSec $HealthTimeoutSec -Label "live $HealthPath"
    if (-not $liveOk) {
        Invoke-Rollback -Reason "live health failed after swap for $targetSha" -RestackLive $true | Out-Null
        Assert-CloudflaredUntouched
        exit 1
    }

    Write-LastGoodSha $targetSha
    Save-LastGoodImages
    Stop-Canary
    Assert-CloudflaredUntouched
    Write-DeployLog "Deploy SUCCESS at $targetSha"
    exit 0
} catch {
    Write-DeployLog "Deploy exception: $_" "ERROR"
    Invoke-Rollback -Reason "exception during deploy of $targetSha : $_" | Out-Null
    Assert-CloudflaredUntouched
    exit 1
}
