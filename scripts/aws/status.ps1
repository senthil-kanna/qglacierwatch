<#
.SYNOPSIS
  Print the current API and dashboard URLs and the health of every part. Read-only.

.DESCRIPTION
  API URL + /health verdict, dashboard task state + URL, schedule states, last job runs.
  -WaitForDashboard polls up to 6 min for the dashboard task to be RUNNING and healthy.
  -Cost adds month-to-date spend from Cost Explorer (each call costs USD 0.01, so it is opt-in).

.EXAMPLE
  ./scripts/aws/status.ps1
  ./scripts/aws/status.ps1 -Cost
#>
param([switch]$WaitForDashboard, [switch]$Cost)

. "$PSScriptRoot/common.ps1"
Assert-Tools
$null = Get-Identity

# --- API ----------------------------------------------------------------------------------------
$api = Get-ApiUrl
if ($api) {
    try {
        $h = Invoke-RestMethod -Uri "${api}health" -TimeoutSec 30
        Write-Check $(if ($h.status -eq 'ok') { 'PASS' } else { 'WARN' }) "API $($h.status): model $($h.model_id) ($($h.model_status))"
        foreach ($p in @($h.problems)) { if ($p) { Write-Check INFO "  $p" } }
    }
    catch { Write-Check FAIL "API did not answer /health: $($_.Exception.Message)" }
}
else { Write-Check WARN 'API not deployed yet (run ./scripts/aws/deploy.ps1 -ImageTag <sha>)' }

# --- dashboard ----------------------------------------------------------------------------------
$dash = $null
$ready = $false
$deadline = (Get-Date).AddMinutes($(if ($WaitForDashboard) { 6 } else { 0 }))
do {
    $svc = Invoke-Aws -Arguments @('ecs', 'describe-services', '--cluster', $script:Project, '--services', "$script:Project-dashboard") -AllowFail
    $s = if ($svc) { @($svc.services)[0] } else { $null }
    if (-not $s -or $s.status -ne 'ACTIVE') { Write-Check WARN 'Dashboard service not deployed yet'; break }
    if ($s.desiredCount -eq 0) { Write-Check INFO 'Dashboard paused (resume: ./scripts/aws/resume.ps1)'; break }
    $dash = Get-DashboardUrl
    $ready = $false
    if ($dash) { try { $ready = (Invoke-WebRequest -Uri "$dash/_stcore/health" -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200 } catch { $ready = $false } }
    if ($ready -or (Get-Date) -ge $deadline) { break }
    Write-Host "  waiting for the dashboard task (running $($s.runningCount)/$($s.desiredCount))..."
    Start-Sleep -Seconds 15
} while ($true)
if ($dash -and $ready) { Write-Check PASS "Dashboard running" }
elseif ($dash) { Write-Check WARN "Dashboard task has an IP but is still starting: $dash" }

# --- schedules and last job runs ----------------------------------------------------------------
foreach ($job in @('refresh', 'drift')) {
    $sch = Invoke-Aws -Arguments @('scheduler', 'get-schedule', '--name', "$script:Project-$job") -AllowFail
    $last = Invoke-Aws -Arguments @('logs', 'describe-log-streams', '--log-group-name', "/aws/lambda/$script:Project-$job",
        '--order-by', 'LastEventTime', '--descending', '--max-items', '1') -AllowFail
    $when = if ($last -and @($last.logStreams).Count) { [DateTimeOffset]::FromUnixTimeMilliseconds(@($last.logStreams)[0].lastEventTimestamp).LocalDateTime } else { 'never' }
    if ($sch) { Write-Check INFO "Job $job : schedule $($sch.State) ($($sch.ScheduleExpression) $($sch.ScheduleExpressionTimezone)), last run $when" }
}

if ($Cost) {
    $start = (Get-Date -Day 1).ToString('yyyy-MM-dd'); $end = (Get-Date).AddDays(1).ToString('yyyy-MM-dd')
    $ce = Invoke-Aws -Arguments @('ce', 'get-cost-and-usage', '--time-period', "Start=$start,End=$end", '--granularity', 'MONTHLY', '--metrics', 'UnblendedCost') -AllowFail
    if ($ce) { $c = @($ce.ResultsByTime)[0].Total.UnblendedCost; Write-Check INFO ("Month-to-date cost: {0:N2} {1} (credits are applied on the bill)" -f [double]$c.Amount, $c.Unit) }
}

# --- the two URLs, clearly ----------------------------------------------------------------------
Write-Banner ("API URL       : {0}" -f $(if ($api) { $api } else { '(not deployed)' })) 'Green'
if ($dash) { Write-Banner "DASHBOARD URL : $dash" 'Green' }
else { Write-Host 'DASHBOARD URL : (no running task)' -ForegroundColor Yellow }
exit 0
