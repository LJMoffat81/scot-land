# Register a free Windows Task Scheduler job that runs uptime-check.ps1 every
# 5 minutes. No paid uptime vendor. Requires running elevated if policy demands.
#
#   .\scripts\ops\register-uptime-task.ps1
#   .\scripts\ops\register-uptime-task.ps1 -Remove

[CmdletBinding()]
param(
    [string]$TaskName = "Scot-LAND-uptime",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$ScriptPath = Join-Path $PSScriptRoot "uptime-check.ps1"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed scheduled task $TaskName"
    exit 0
}

if (-not (Test-Path $ScriptPath)) {
    throw "Missing $ScriptPath"
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration ([TimeSpan]::MaxValue)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Scot-LAND free uptime probe (https://scot-land.scot/backend/health every 5 min)" `
    -Force | Out-Null

Write-Host "Registered $TaskName -> $ScriptPath every 5 minutes"
Write-Host "Logs: $(Join-Path $RepoRoot '.deploy\uptime.log')"
