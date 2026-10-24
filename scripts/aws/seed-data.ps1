<#
.SYNOPSIS
  Upload the data, models and reports the cloud services read to the project bucket.

.DESCRIPTION
  Syncs these local folders to s3://<bucket>/<same path> (aws s3 sync: only new/changed files):
    data/raw  data/processed/real  artifacts/real  reports/real
  NEVER uploaded: data/external (private gauge data), demo/synthetic outputs, *.log files.
  Shows a dry run first and asks before uploading. Roughly 110 MB; S3 storage cost < USD 0.01/month.

.EXAMPLE
  ./scripts/aws/seed-data.ps1
#>
param([switch]$Yes)

. "$PSScriptRoot/common.ps1"
Assert-Tools
Show-Target (Get-Identity)
$bucket = Get-TfOutput 'bucket'
if (-not $bucket) { throw 'No bucket in Terraform outputs. Run ./scripts/aws/bootstrap.ps1 first.' }

$parts = @('data/raw', 'data/processed/real', 'artifacts/real', 'reports/real')
$exclude = @('--exclude', '*.log', '--exclude', '*.tmp', '--exclude', '.gitkeep')
foreach ($p in $parts) {
    if (-not (Test-Path (Join-Path $script:RepoRoot $p))) { throw "Missing local folder $p (run the pipeline or `dvc pull` first)." }
}

Write-Host "`n=== Dry run: files that would be uploaded to s3://$bucket ===" -ForegroundColor Cyan
$total = 0
foreach ($p in $parts) {
    $lines = @(& aws s3 sync (Join-Path $script:RepoRoot $p) "s3://$bucket/$p" @exclude --dryrun --region $script:Region)
    if ($LASTEXITCODE -ne 0) { throw "aws s3 sync --dryrun failed for $p" }
    $n = @($lines | Where-Object { $_ -match 'upload:' }).Count
    $total += $n
    Write-Host ("  {0,-22} {1} file(s)" -f $p, $n)
}
if ($total -eq 0) { Write-Check PASS 'S3 already up to date. Nothing to upload.'; exit 0 }

Confirm-Step -Message "Upload $total file(s) to s3://$bucket ?" -Yes:$Yes
foreach ($p in $parts) {
    & aws s3 sync (Join-Path $script:RepoRoot $p) "s3://$bucket/$p" @exclude --only-show-errors --region $script:Region
    if ($LASTEXITCODE -ne 0) { throw "upload failed for $p" }
    Write-Check PASS "$p -> s3://$bucket/$p"
}
Write-Host 'Done. The dashboard re-reads reports/features from S3 every 15 min; the API at each cold start.'
