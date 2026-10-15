# Register a daily Windows Task Scheduler job for pg-dump-daily.ps1.
# Keeps 14 dated dumps (see the dump script). Requires elevation if policy demands.
#
#   .\scripts\ops\register-pg-dump-task.ps1
#   .\scripts\ops\register-pg-dump-task.ps1 -Remove
#
# Task Scheduler notes (HOME-TUNNEL):
#   - Trigger: Daily at 02:30 local (adjust as needed).
#   - Action: powershell.exe -NoProfile -ExecutionPolicy Bypass -File <pg-dump-daily.ps1>
#   - Run whether user is logged on or not (store the Windows password in the task).
#   - Ensure PostgreSQL client tools (pg_dump) are on PATH for that account.
#   - PGPASSWORD / POSTGRES_PASSWORD must be available to the task (User env or
#     a machine-local .env next to the repo — never commit secrets).

[CmdletBinding()]
param(
    [string]$TaskName = "Scot-LAND-pg-dump-daily",
    [string]$At = "02:30",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$ScriptPath = Join-Path $PSScriptRoot "pg-dump-daily.ps1"

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
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings `
    -Description "Scot-LAND daily dated pg_dump (keeps 14 copies; HOME-TUNNEL)" `
    -Force | Out-Null

Write-Host "Registered $TaskName → $ScriptPath daily at $At"
Write-Host "Dumps default to <repo>\.deploy\pg-dumps\ (gitignored). Keep=14."
