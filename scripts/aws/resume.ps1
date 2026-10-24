<#
.SYNOPSIS
  Start the dashboard again (and the weekly schedules), wait for it, and print its new URL.

.DESCRIPTION
  Sets dashboard_enabled=true and schedules_enabled=true, applies, waits until the Fargate task is
  RUNNING and healthy, then prints DASHBOARD URL http://<public ip>:8501 in a banner. The IP is new
  after every resume; it stays the same as long as the task keeps running (do not pause during
  presentation week). Also warms the API with one /health call.

.EXAMPLE
  ./scripts/aws/resume.ps1
#>
param([switch]$Yes)

. "$PSScriptRoot/common.ps1"
Assert-Tools
Show-Target (Get-Identity)
Set-TfVars @{ dashboard_enabled = 'true'; schedules_enabled = 'true' }
Invoke-TfApply -Why 'start the dashboard task (desired count 1) and enable schedules' -Yes:$Yes
& "$PSScriptRoot/status.ps1" -WaitForDashboard
