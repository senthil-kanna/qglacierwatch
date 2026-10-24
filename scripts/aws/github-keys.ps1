<#
.SYNOPSIS
  Gives GitHub Actions the CI deploy user's access key, stored only as GitHub repository secrets.

.DESCRIPTION
  The project's managed SCP denies GitHub OIDC (iam:*Provider*), so the aws-deploy job signs in as
  the IAM user qglacierwatch-github-deploy (created by bootstrap.ps1; it can only push images and
  roll the functions and the dashboard). This script:
  1. Creates an access key for that user (asks first). The key is never printed or written to disk:
     it goes straight from the AWS CLI into `gh secret set` (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY).
  2. Sets the repository variable AWS_DEPLOY_ENABLED=true, which switches the aws-deploy job on.
  -Rotate creates a new key, stores it, then deletes the old one.
  -Revoke deletes every key of the user and the GitHub secrets/variable (do this after the
  presentation, or at once if a key may have leaked).

.EXAMPLE
  ./scripts/aws/github-keys.ps1
  ./scripts/aws/github-keys.ps1 -Rotate
  ./scripts/aws/github-keys.ps1 -Revoke
#>
param(
    [switch]$Rotate,
    [switch]$Revoke,
    [switch]$Yes,
    [string]$Repo = 'senthil-kanna/qglacierwatch'
)

. "$PSScriptRoot/common.ps1"
Assert-Tools
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI missing: winget install -e --id GitHub.cli, then gh auth login (new terminal).' }
$id = Get-Identity
Show-Target $id
$user = "$script:Project-github-deploy"
$secrets = @('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY')

function Invoke-Gh {
    param([Parameter(Mandatory)][string[]]$Arguments, [string]$InputText)
    if ($PSBoundParameters.ContainsKey('InputText')) { $InputText | & gh @Arguments } else { & gh @Arguments }
    if ($LASTEXITCODE -ne 0) { throw "gh $($Arguments[0..1] -join ' ') failed (exit $LASTEXITCODE)" }
}

$listed = Invoke-Aws -Arguments @('iam', 'list-access-keys', '--user-name', $user) -AllowFail
if (-not $listed) { throw "IAM user $user not found. Run ./scripts/aws/bootstrap.ps1 first." }
$old = @($listed.AccessKeyMetadata | ForEach-Object { $_.AccessKeyId })
Write-Host "`n=== $user : $($old.Count) existing key(s) ===" -ForegroundColor Cyan
$old | ForEach-Object { Write-Host "  $_" }

if ($Revoke) {
    Confirm-Step -Message "Delete all $($old.Count) key(s) of $user and the GitHub secrets $($secrets -join ', ') in $Repo?" -Yes:$Yes
    foreach ($k in $old) {
        Invoke-Aws -Arguments @('iam', 'delete-access-key', '--user-name', $user, '--access-key-id', $k) -Raw | Out-Null
        Write-Check PASS "deleted key $k"
    }
    foreach ($s in $secrets) { & gh secret delete $s --repo $Repo 2>$null; Write-Check PASS "GitHub secret $s removed" }
    & gh variable delete AWS_DEPLOY_ENABLED --repo $Repo 2>$null
    Write-Check PASS 'aws-deploy job switched off (AWS_DEPLOY_ENABLED removed).'
    exit 0
}

if ($old.Count -ge 2) { throw "$user already has 2 keys (the AWS maximum). Run -Revoke first." }
if ($old.Count -eq 1 -and -not $Rotate) { throw "$user already has key $($old[0]). Use -Rotate to replace it, or -Revoke." }
Confirm-Step -Message "Create a new access key for $user and store it as GitHub secrets in $Repo$(if ($Rotate) { ', then delete the old key' })?" -Yes:$Yes

$key = Invoke-Aws -Arguments @('iam', 'create-access-key', '--user-name', $user)
try {
    Invoke-Gh -Arguments @('secret', 'set', 'AWS_ACCESS_KEY_ID', '--repo', $Repo) -InputText $key.AccessKey.AccessKeyId
    Invoke-Gh -Arguments @('secret', 'set', 'AWS_SECRET_ACCESS_KEY', '--repo', $Repo) -InputText $key.AccessKey.SecretAccessKey
}
catch {
    Invoke-Aws -Arguments @('iam', 'delete-access-key', '--user-name', $user, '--access-key-id', $key.AccessKey.AccessKeyId) -Raw -AllowFail | Out-Null
    throw "Storing the secrets failed, so the new key was deleted again ($_). Check gh auth status."
}
$newId = $key.AccessKey.AccessKeyId
$key = $null
Write-Check PASS "key $newId stored as GitHub secrets $($secrets -join ', ') (value not shown)"
Invoke-Gh -Arguments @('variable', 'set', 'AWS_DEPLOY_ENABLED', '--repo', $Repo, '--body', 'true')
Write-Check PASS 'aws-deploy job switched on (repository variable AWS_DEPLOY_ENABLED=true).'

if ($Rotate) {
    foreach ($k in $old) {
        Invoke-Aws -Arguments @('iam', 'delete-access-key', '--user-name', $user, '--access-key-id', $k) -Raw | Out-Null
        Write-Check PASS "deleted old key $k"
    }
}
Write-Host 'Next: gh workflow run ci.yml --ref feat/aws-deployment   (after pushing the branch)'
Write-Host 'After the presentation: ./scripts/aws/github-keys.ps1 -Revoke'
