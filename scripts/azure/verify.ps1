<#
.SYNOPSIS
  Verify a deployed QGlacierWatch: endpoints, auth, data on the share, alerts, revisions. Read-only
  unless -WriteTest is given.

.DESCRIPTION
  PASS only when the check actually succeeded against Azure. Checks:
    - API /health reachable (cold start allowed) and reports a model; problems are listed
    - /v1/forecast rejects a request without X-API-Key (401) and accepts the Key Vault key (200)
    - dashboard /_stcore/health
    - Azure Files share holds the uploaded data, registry and reports (storage connectivity)
    - metric alert rules and action group exist and are enabled
    - revisions listed for rollback
  -WriteTest starts the drift job and confirms it wrote a new file to the share (mount + write
  permissions + persistence across containers). Billed per second (~2 min at 0.5 vCPU).
#>
param(
    [string]$ResourceGroup = 'rg-qglacierwatch',
    [switch]$WriteTest,
    [int]$ColdStartSeconds = 300
)

. "$PSScriptRoot/common.ps1"
Assert-AzCli
$acct = Get-CurrentAccount
Write-Check INFO "Subscription $($acct.name), resource group $ResourceGroup"
$fails = 0
function Fail([string]$m) { Write-Check FAIL $m; $script:fails++ }

function Get-Url([string]$path, [hashtable]$headers = @{}) {
    try { $r = Invoke-WebRequest -Uri $path -Headers $headers -UseBasicParsing -TimeoutSec 60; return @{ code = [int]$r.StatusCode; body = $r.Content } }
    catch {
        $resp = $_.Exception.Response
        if ($resp) { return @{ code = [int]$resp.StatusCode; body = '' } }
        return @{ code = 0; body = $_.Exception.Message }
    }
}

$apiFqdn = (& az containerapp show -g $ResourceGroup -n qgw-api --query properties.configuration.ingress.fqdn -o tsv 2>$null)
$dashFqdn = (& az containerapp show -g $ResourceGroup -n qgw-dashboard --query properties.configuration.ingress.fqdn -o tsv 2>$null)
if (-not $apiFqdn) { Fail 'qgw-api not found (apps not deployed?)'; exit 1 }

# Health with cold start: the app is scaled to zero until the first request.
$deadline = (Get-Date).AddSeconds($ColdStartSeconds); $h = $null
while ((Get-Date) -lt $deadline) {
    $h = Get-Url "https://$apiFqdn/health"
    if ($h.code -eq 200) { break }
    Start-Sleep -Seconds 15
}
if ($h.code -eq 200) {
    $hj = $h.body | ConvertFrom-Json
    Write-Check PASS "API health https://$apiFqdn/health -> status=$($hj.status), model=$($hj.model_id) ($($hj.model_status))"
    foreach ($p in $hj.problems) { Write-Check WARN "health: $p" }
    if (-not $hj.model_id) { Fail 'API sees no model: registry not on the share or mount failed' }
} else { Fail "API health not reachable within $ColdStartSeconds s (last: $($h.code) $($h.body))" }

# Auth and inference.
$noKey = Get-Url "https://$apiFqdn/v1/forecast"
if ($noKey.code -eq 401) { Write-Check PASS '/v1/forecast without key -> 401 (API key enforced)' } else { Fail "/v1/forecast without key returned $($noKey.code), expected 401" }
$kv = (& az keyvault list -g $ResourceGroup --query '[0].name' -o tsv)
$key = (& az keyvault secret show --vault-name $kv -n qgw-api-key --query value -o tsv 2>$null)
if ($key) {
    $f = Get-Url "https://$apiFqdn/v1/forecast" @{ 'X-API-Key' = $key }
    if ($f.code -eq 200) {
        $fj = $f.body | ConvertFrom-Json
        Write-Check PASS "/v1/forecast with key -> 200, issue $($fj.issue_date), $(@($fj.forecasts).Count) horizons, model $($fj.model_id)"
    } else { Fail "/v1/forecast with key returned $($f.code)" }
} else { Write-Check WARN 'Could not read qgw-api-key from Key Vault (need Key Vault Secrets User/Officer)' }
$key = $null

# Dashboard.
if ($dashFqdn) {
    $deadline = (Get-Date).AddSeconds($ColdStartSeconds); $d = $null
    while ((Get-Date) -lt $deadline) { $d = Get-Url "https://$dashFqdn/_stcore/health"; if ($d.code -eq 200) { break }; Start-Sleep -Seconds 15 }
    if ($d.code -eq 200) { Write-Check PASS "Dashboard https://$dashFqdn healthy" } else { Fail "Dashboard health returned $($d.code)" }
}

# Storage connectivity: the share holds what the apps read.
$st = (& az storage account list -g $ResourceGroup --query '[0].name' -o tsv)
foreach ($dir in 'data/raw', 'data/processed', 'artifacts/real/registry', 'reports/real') {
    $n = @(Invoke-AzJson -Arguments @('storage', 'file', 'list', '--account-name', $st, '--share-name', 'qgw', '--path', $dir, '--auth-mode', 'key') -AllowFail).Count
    if ($n -gt 0) { Write-Check PASS "Share qgw/$dir has $n entries" } else { Fail "Share qgw/$dir is empty or unreadable" }
}

# Alerts.
$rules = @(Invoke-AzJson -Arguments @('monitor', 'metrics', 'alert', 'list', '-g', $ResourceGroup) -AllowFail)
foreach ($r in $rules) { if ($r.enabled) { Write-Check PASS "Alert rule $($r.name) enabled" } else { Fail "Alert rule $($r.name) disabled" } }
if ($rules.Count -eq 0) { Write-Check WARN 'No metric alert rules found (enableAlerts=false?)' }
$ag = Invoke-AzJson -Arguments @('monitor', 'action-group', 'list', '-g', $ResourceGroup, '--query', '[0]') -AllowFail
if ($ag) { Write-Check PASS "Action group $($ag.name) -> $(@($ag.emailReceivers).emailAddress -join ', ') (confirm the Azure e-mail if asked)" }

# Rollback readiness.
$revs = @(Invoke-AzJson -Arguments @('containerapp', 'revision', 'list', '-g', $ResourceGroup, '-n', 'qgw-api', '--query', '[].{name:name,active:properties.active,created:properties.createdTime}') -AllowFail)
Write-Check INFO "API revisions: $($revs.Count) (rollback: az containerapp ingress traffic set -g $ResourceGroup -n qgw-api --revision-weight <previous-revision>=100)"

# Optional write test through a job (mount, permissions, persistence).
if ($WriteTest) {
    $before = Get-Date
    & az containerapp job start -g $ResourceGroup -n qgw-job-drift -o none
    Write-Check INFO 'Started qgw-job-drift; waiting up to 15 min for completion'
    $status = ''
    for ($i = 0; $i -lt 60 -and $status -notin 'Succeeded', 'Failed'; $i++) {
        Start-Sleep -Seconds 15
        $status = (& az containerapp job execution list -g $ResourceGroup -n qgw-job-drift --query '[0].properties.status' -o tsv)
    }
    if ($status -ne 'Succeeded') { Fail "Drift job ended with status '$status' (see: az containerapp job logs show -g $ResourceGroup -n qgw-job-drift)" }
    else {
        $files = @(Invoke-AzJson -Arguments @('storage', 'file', 'list', '--account-name', $st, '--share-name', 'qgw', '--path', 'reports/real', '--auth-mode', 'key', '--include-times') -AllowFail)
        $new = $files | Where-Object { $_.name -eq 'drift_latest.json' -and $_.properties.lastModified -and ([datetime]$_.properties.lastModified).ToUniversalTime() -gt $before.ToUniversalTime() }
        if ($new) { Write-Check PASS 'Job wrote reports/real/drift_latest.json to the share (mount, write permission and persistence verified)' }
        else { Fail 'Job succeeded but reports/real/drift_latest.json was not updated on the share' }
    }
}

Write-Host ''
if ($fails -gt 0) { Write-Check FAIL "$fails verification check(s) failed."; exit 1 }
Write-Check PASS 'Deployment verified.'
exit 0
