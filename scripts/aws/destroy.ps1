<#
.SYNOPSIS
  Full teardown after the presentation: deletes every QGlacierWatch resource, and nothing else.

.DESCRIPTION
  1. Lists every resource tagged project=qglacierwatch in ap-south-1 (plus global IAM/budget).
  2. You must type the project name exactly (or pass -ConfirmName qglacierwatch).
  3. Empties the versioned S3 bucket (all object versions), then `terraform destroy` (asks again).
  4. Deletes the /qgw/* SSM parameters, then lists anything still tagged (should be empty).
  -DryRun stops after step 1. -Orphans (if the Terraform state was lost) only LISTS tagged
  resources with the console pages to delete them; it deletes nothing.
  Download anything you want to keep from S3 first (aws s3 sync s3://<bucket> ./backup).

.EXAMPLE
  ./scripts/aws/destroy.ps1 -DryRun
  ./scripts/aws/destroy.ps1
#>
param([switch]$DryRun, [switch]$Orphans, [string]$ConfirmName = '')

. "$PSScriptRoot/common.ps1"
Assert-Tools
$id = Get-Identity
Show-Target $id

function Get-Tagged {
    $r = Invoke-Aws -Arguments @('resourcegroupstaggingapi', 'get-resources', '--tag-filters', "Key=project,Values=$script:Project") -AllowFail
    return @(if ($r) { $r.ResourceTagMappingList | ForEach-Object { $_.ResourceARN } })
}

$tagged = Get-Tagged
Write-Host "`n=== Resources tagged project=$script:Project ($($tagged.Count)) ===" -ForegroundColor Cyan
$tagged | ForEach-Object { Write-Host "  $_" }
if ($DryRun) { Write-Check INFO 'Dry run: nothing deleted.'; exit 0 }
if ($Orphans) {
    Write-Host "`nDelete these in the console (ap-south-1): Lambda, ECS (cluster $script:Project), ECR, S3 (empty first),"
    Write-Host 'EventBridge Scheduler, CloudWatch (log groups /aws/lambda/qglacierwatch-*, /ecs/qglacierwatch-*, alarms),'
    Write-Host 'SNS, SSM /qgw/*, VPC security group qglacierwatch-dashboard, IAM roles qglacierwatch-*, the GitHub OIDC'
    Write-Host 'provider, and Budgets qglacierwatch-monthly. Nothing was deleted.'
    exit 0
}

if (-not $ConfirmName) { $ConfirmName = Read-Host "Type the project name '$script:Project' to delete everything above" }
if ($ConfirmName -ne $script:Project) { Write-Check FAIL 'Name did not match. Nothing deleted.'; exit 2 }

$bucket = Get-TfOutput 'bucket'
if ($bucket) {
    Write-Host "`n=== Emptying s3://$bucket (all versions) ===" -ForegroundColor Cyan
    do {
        $v = Invoke-Aws -Arguments @('s3api', 'list-object-versions', '--bucket', $bucket, '--max-items', '500') -AllowFail
        $objs = @()
        if ($v) { $objs = @($v.Versions) + @($v.DeleteMarkers) | Where-Object { $_ } | ForEach-Object { @{ Key = $_.Key; VersionId = $_.VersionId } } }
        if ($objs.Count -eq 0) { break }
        $tmp = New-TemporaryFile
        try {
            [IO.File]::WriteAllText($tmp.FullName, (@{ Objects = @($objs); Quiet = $true } | ConvertTo-Json -Depth 4))
            Invoke-Aws -Arguments @('s3api', 'delete-objects', '--bucket', $bucket, '--delete', "file://$($tmp.FullName)") | Out-Null
        }
        finally { Remove-Item $tmp.FullName -Force }
        Write-Host "  deleted $($objs.Count) object version(s)"
    } while ($true)
}

Write-Host "`n=== terraform destroy ===" -ForegroundColor Cyan
try { Invoke-Terraform -Arguments @('destroy', '-input=false') }
finally { Backup-TfState }

foreach ($p in $script:SsmParams) {
    if (Invoke-Aws -Arguments @('ssm', 'delete-parameter', '--name', $p) -AllowFail -Raw) { Write-Check PASS "deleted $p" }
}

$left = Get-Tagged
if ($left.Count) { Write-Check WARN "Still tagged (may take minutes to disappear from the tag index):"; $left | ForEach-Object { Write-Host "  $_" } }
else { Write-Check PASS 'No tagged resources left.' }
Write-Host 'Your own zero-spend budget and AWS account settings were not touched.'
