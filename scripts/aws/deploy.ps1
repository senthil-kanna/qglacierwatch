<#
.SYNOPSIS
  Full deploy: create/update all infrastructure and roll the API, jobs and dashboard to an image tag.

.DESCRIPTION
  -ImageTag is the git commit SHA whose images the CI aws-deploy job pushed to ECR (also usable to
  roll BACK to an older SHA that is still in ECR; the last 3 images are kept).
  1. Checks that qglacierwatch-api:<tag>, qglacierwatch-app:<tag> and app:live exist in ECR.
  2. terraform plan/apply with create_compute=true (asks first; state is backed up afterwards).
  3. Points the three Lambdas at <tag> (aws lambda update-function-code) and restarts the
     dashboard task if it is running (its public IP changes).
  4. Prints status (API URL, dashboard URL).

.EXAMPLE
  ./scripts/aws/deploy.ps1 -ImageTag 3d38b7d0c1...   # full 40-character SHA
#>
param(
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{7,40}$')][string]$ImageTag,
    [switch]$Yes
)

. "$PSScriptRoot/common.ps1"
Assert-Tools
Show-Target (Get-Identity)
if (-not (Test-Path $script:TfVars)) { throw 'infra/aws/terraform.tfvars missing. Run ./scripts/aws/bootstrap.ps1 first.' }

Write-Host "`n=== Images in ECR ===" -ForegroundColor Cyan
foreach ($img in @(@('api', $ImageTag), @('app', $ImageTag), @('app', 'live'))) {
    $found = Invoke-Aws -Arguments @('ecr', 'describe-images', '--repository-name', "$script:Project-$($img[0])", '--image-ids', "imageTag=$($img[1])") -AllowFail
    if (-not $found) { throw "Image $script:Project-$($img[0]):$($img[1]) not in ECR. Run the CI workflow (gh workflow run ci.yml --ref <branch>) and use its SHA." }
    Write-Check PASS "$script:Project-$($img[0]):$($img[1])"
}

Write-Host "`n=== Infrastructure ===" -ForegroundColor Cyan
Set-TfVars @{ create_compute = 'true'; api_image_tag = $ImageTag; app_image_tag = $ImageTag }
Invoke-TfApply -Why 'create or update the API Lambda + URL, job Lambdas, schedules, dashboard service and alarms' -Yes:$Yes

Write-Host "`n=== Roll out image $ImageTag ===" -ForegroundColor Cyan
$reg = "$((Get-Identity).Account).dkr.ecr.$script:Region.amazonaws.com"
$targets = @{ api = "$reg/$script:Project-api:$ImageTag"; refresh = "$reg/$script:Project-app:$ImageTag"; drift = "$reg/$script:Project-app:$ImageTag" }
foreach ($fn in $targets.Keys) {
    & aws lambda wait function-active-v2 --function-name "$script:Project-$fn" --region $script:Region
    Invoke-Aws -Arguments @('lambda', 'update-function-code', '--function-name', "$script:Project-$fn", '--image-uri', $targets[$fn]) | Out-Null
}
foreach ($fn in $targets.Keys) {
    & aws lambda wait function-updated-v2 --function-name "$script:Project-$fn" --region $script:Region
    Write-Check PASS "$script:Project-$fn -> $($targets[$fn])"
}
$svc = Invoke-Aws -Arguments @('ecs', 'describe-services', '--cluster', $script:Project, '--services', "$script:Project-dashboard") -AllowFail
if ($svc -and @($svc.services)[0].desiredCount -gt 0) {
    Invoke-Aws -Arguments @('ecs', 'update-service', '--cluster', $script:Project, '--service', "$script:Project-dashboard", '--force-new-deployment') | Out-Null
    Write-Check INFO 'Dashboard restarting on app:live (1-3 min). Its public IP will change.'
}

& "$PSScriptRoot/status.ps1" -WaitForDashboard
