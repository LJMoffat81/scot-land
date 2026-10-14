# Backward-compatible entry point for home PC auto-deploy.
# Delegates to the health-gated swap in deploy-home.ps1 (never stops cloudflared).
#
# Usage:
#   .\scripts\ops\rebuild-home.ps1
#   .\scripts\ops\rebuild-home.ps1 -Pull

[CmdletBinding()]
param(
    [switch]$Pull
)

$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
& (Join-Path $here "deploy-home.ps1") @PSBoundParameters
exit $LASTEXITCODE
