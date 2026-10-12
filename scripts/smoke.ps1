# Mandatory post-deploy smoke for Scot-LAND.
# Usage:
#   .\scripts\smoke.ps1 -BaseUrl https://example.com
#   .\scripts\smoke.ps1 -SiteUrl https://app.example -ApiUrl https://api.example
# Exit non-zero when any check fails.

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$BaseUrl = "",
    [string]$SiteUrl = "",
    [string]$ApiUrl = ""
)

$ErrorActionPreference = "Stop"

if (-not $SiteUrl) { $SiteUrl = $BaseUrl }
if (-not $ApiUrl) { $ApiUrl = $(if ($SiteUrl) { $SiteUrl } else { $BaseUrl }) }

if (-not $SiteUrl -or -not $ApiUrl) {
    Write-Error "Usage: .\scripts\smoke.ps1 -BaseUrl https://example.com"
    exit 2
}

$SiteUrl = $SiteUrl.TrimEnd("/")
$ApiUrl = $ApiUrl.TrimEnd("/")
$Bbox = "south=54.6&west=-7.7&north=60.9&east=-0.7&max_features=80"

$pass = 0
$fail = 0
$rows = New-Object System.Collections.Generic.List[string]

function Add-Row([string]$Status, [string]$Name, [string]$Detail) {
    $script:rows.Add(("{0,-6} | {1,-40} | {2}" -f $Status, $Name, $Detail))
    if ($Status -eq "PASS") { $script:pass++ } else { $script:fail++ }
}

function Invoke-SmokeGet([string]$Url) {
    try {
        $resp = Invoke-WebRequest -Uri $Url -Method GET -TimeoutSec 45 -UseBasicParsing
        return @{ Code = [int]$resp.StatusCode; Body = $resp.Content }
    } catch {
        $ex = $_.Exception
        $code = 0
        if ($ex.Response -and $ex.Response.StatusCode) {
            $code = [int]$ex.Response.StatusCode
            try {
                $reader = New-Object System.IO.StreamReader($ex.Response.GetResponseStream())
                $body = $reader.ReadToEnd()
                $reader.Close()
                return @{ Code = $code; Body = $body }
            } catch {
                return @{ Code = $code; Body = "" }
            }
        }
        return @{ Code = 0; Body = "$ex" }
    }
}

Write-Host "Scot-LAND post-deploy smoke"
Write-Host "  SITE_URL=$SiteUrl"
Write-Host "  API_URL=$ApiUrl"
Write-Host ""

$r = Invoke-SmokeGet "$SiteUrl/"
if ($r.Code -eq 200) { Add-Row "PASS" "site /" "HTTP $($r.Code)" }
else { Add-Row "FAIL" "site /" "HTTP $($r.Code) (want 200)" }

$r = Invoke-SmokeGet "$ApiUrl/health"
if ($r.Code -eq 200) {
    try {
        $health = $r.Body | ConvertFrom-Json
        $commit = [string]$health.git_commit
        if ($commit) { Add-Row "PASS" "/health" "HTTP 200 git_commit=$commit" }
        else { Add-Row "FAIL" "/health" "HTTP 200 but git_commit missing/empty" }
    } catch {
        Add-Row "FAIL" "/health" "HTTP 200 but body is not JSON"
    }
} else {
    Add-Row "FAIL" "/health" "HTTP $($r.Code) (want 200)"
}

$r = Invoke-SmokeGet "$ApiUrl/layers/catalog"
if ($r.Code -ne 200) {
    Add-Row "FAIL" "/layers/catalog" "HTTP $($r.Code) (want 200)"
} else {
    Add-Row "PASS" "/layers/catalog" "HTTP 200"
    $catalog = $r.Body | ConvertFrom-Json
    foreach ($layer in @($catalog.layers)) {
        if (-not $layer) { continue }
        if ([string]$layer.status -ne "live") { continue }
        $endpoint = [string]$layer.endpoint
        if (-not $endpoint.StartsWith("/")) { continue }
        if ($endpoint.Contains("{z}") -or $endpoint.Contains("{x}")) { continue }
        $lid = [string]$layer.id
        if ($endpoint.Contains("?")) { $full = "$ApiUrl$endpoint" }
        else { $full = "$ApiUrl${endpoint}?$Bbox" }
        $lr = Invoke-SmokeGet $full
        if ($lr.Code -eq 200) {
            try {
                $payload = $lr.Body | ConvertFrom-Json
                if ($null -ne $payload.features) {
                    $n = @($payload.features).Count
                    if ($n -gt 0) { Add-Row "PASS" "layer:$lid" "HTTP 200 features=$n" }
                    else { Add-Row "FAIL" "layer:$lid" "HTTP 200 features=0 (want >0 or 503 not-yet-loaded)" }
                } else {
                    Add-Row "PASS" "layer:$lid" "HTTP 200 (non-FeatureCollection OK)"
                }
            } catch {
                Add-Row "FAIL" "layer:$lid" "HTTP 200 but body is not JSON"
            }
        } elseif ($lr.Code -eq 503) {
            $detail = "not loaded"
            try {
                $payload = $lr.Body | ConvertFrom-Json
                if ($payload.detail) { $detail = [string]$payload.detail }
                elseif ($payload.meta -and $payload.meta.error) { $detail = [string]$payload.meta.error }
            } catch { }
            if ($detail.Length -gt 120) { $detail = $detail.Substring(0, 120) }
            Add-Row "PASS" "layer:$lid" "HTTP 503 not-yet-loaded ($detail)"
        } else {
            Add-Row "FAIL" "layer:$lid" "HTTP $($lr.Code) (want 200+features or 503 unload)"
        }
    }
}

Write-Host ""
Write-Host "STATUS | CHECK                                    | DETAIL"
Write-Host "-------+------------------------------------------+----------------------------------------"
foreach ($row in $rows) { Write-Host $row }
Write-Host ""
Write-Host "Summary: PASS=$pass FAIL=$fail"

if ($fail -gt 0) {
    Write-Error "SMOKE FAILED"
    exit 1
}
Write-Host "SMOKE PASSED"
exit 0
