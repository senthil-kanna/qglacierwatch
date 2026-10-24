<#
.SYNOPSIS
  Save credits between demos: stop the dashboard task and (by default) the weekly schedules.

.DESCRIPTION
  Sets dashboard_enabled=false (and schedules_enabled=false unless -KeepSchedules) and applies.
  The API Lambda already scales to zero and costs nothing while idle, so it stays reachable.
  Saves about USD 0.75/day (Fargate 0.5 vCPU/1 GB + public IPv4). Nothing is deleted.
  From 5 Nov (presentation week) leave the dashboard running so its IP stays the same.

.EXAMPLE
  ./scripts/aws/pause.ps1
#>
param([switch]$KeepSchedules, [switch]$Yes)

. "$PSScriptRoot/common.ps1"
Assert-Tools
Show-Target (Get-Identity)
$values = @{ dashboard_enabled = 'false' }
if (-not $KeepSchedules) { $values['schedules_enabled'] = 'false' }
Set-TfVars $values
Invoke-TfApply -Why 'stop the dashboard task (desired count 0) and pause schedules as listed' -Yes:$Yes
Write-Banner 'Paused. API still answers (scales to zero). Resume with ./scripts/aws/resume.ps1' 'Yellow'
