<#
.SYNOPSIS
  Deploy QGlacierWatch to Azure (resource group, base infrastructure, secrets, data, apps).

.DESCRIPTION
  Runs preflight.ps1, shows the target subscription / resource group / region / image and the
  cost estimate, and asks you to type the resource-group name before anything is created.
  Steps (each idempotent; safe to re-run):
    1. resource group (tag project=qglacierwatch); refuses an existing group without that tag
    2. base infrastructure (what-if preview, then deploy; apps off)
    3. Key Vault secrets: API key (generated once, never overwritten) and Earth Engine key
       (-EeKeyFile, or a placeholder so the apps can start; ingestion then fails clearly)
    4. upload data/raw, data/processed, artifacts/real and reports/real to the Azure Files share
    5. apps, jobs and alerts with the GHCR image tag (skip with -BaseOnly)
    6. verification: /health, /v1/forecast with the API key, dashboard health, alert rules
  Nothing here deletes resources; use cleanup.ps1 for that.

.EXAMPLE
  ./scripts/azure/deploy.ps1 -AlertEmail you@example.com -ImageTag <git-sha>
#>
param(
    [Parameter(Mandatory)][string]$AlertEmail,
    [string]$ImageTag = '',
    [string]$Location = 'centralindia',
    [string]$ResourceGroup = 'rg-qglacierwatch',
    [string]$Image = 'ghcr.io/senthil-kanna/qglacierwatch',
    [string]$EeKeyFile = '',
    [int]$MonthlyBudgetUsd = 20,
    [switch]$BaseOnly,
    [string]$ConfirmName = ''   # non-interactive confirmation; must equal -ResourceGroup
)

. "$PSScriptRoot/common.ps1"
$root = Resolve-Path "$PSScriptRoot/../.."
$template = Join-Path $root 'infra/main.bicep'
$params = Join-Path $root 'infra/main.parameters.json'
Assert-AzCli
$acct = Get-CurrentAccount
if (-not $BaseOnly -and -not $ImageTag) { throw 'Pass -ImageTag <git-sha> (from the GitHub "image" workflow), or -BaseOnly.' }

# Pre-flight (read-only). Stops here if anything fails.
$pfArgs = @{ Location = $Location; ResourceGroup = $ResourceGroup; Image = $Image }
if ($ImageTag) { $pfArgs.ImageTag = $ImageTag }
& "$PSScriptRoot/preflight.ps1" @pfArgs
if ($LASTEXITCODE -ne 0) { throw 'Pre-flight failed; nothing was created.' }

Write-Host ''
Write-Host '=== Deployment target ===' -ForegroundColor Cyan
Write-Host "Subscription : $($acct.name) ($($acct.id))"
Write-Host "Resource grp : $ResourceGroup   Region: $Location"
Write-Host "Image        : $(if ($BaseOnly) { '(base only, no apps)' } else { "${Image}:$ImageTag" })"
Write-Host "Budget alert : USD $MonthlyBudgetUsd/month -> $AlertEmail"
Write-Host 'Estimate     : ~USD 0-1/month inside free grants (estimate, not a guarantee; see docs/deployment.md)'
$answer = if ($ConfirmName) { $ConfirmName } else { Read-Host "Type the resource group name ($ResourceGroup) to deploy, anything else to cancel" }
if ($answer -ne $ResourceGroup) { Write-Check INFO 'Cancelled; nothing was created.'; exit 2 }

# 1. Resource group: create, or reuse only if it is ours.
$rg = Invoke-AzJson -Arguments @('group', 'show', '-n', $ResourceGroup) -AllowFail
if ($rg) {
    if ($rg.tags.project -ne $ProjectTag) { throw "Resource group $ResourceGroup exists without tag project=$ProjectTag; refusing to deploy into it." }
    Write-Check INFO "Reusing resource group $ResourceGroup"
} else {
    Invoke-AzJson -Arguments @('group', 'create', '-n', $ResourceGroup, '-l', $Location, '--tags', "project=$ProjectTag") | Out-Null
    Write-Check PASS "Created resource group $ResourceGroup"
}

# 2. Base infrastructure (no apps yet): preview, then deploy.
$oid = (& az ad signed-in-user show --query id -o tsv 2>$null)
$budgetStart = (Get-Date -Day 1).ToString('yyyy-MM-01')
$common = @('-g', $ResourceGroup, '-f', $template, '-p', $params, '-p',
    "location=$Location", "alertEmail=$AlertEmail", "budgetStartDate=$budgetStart", "monthlyBudgetUsd=$MonthlyBudgetUsd",
    "useAcr=false", "externalImage=$Image", "adminPrincipalId=$oid")
& az deployment group what-if @common -p deployApps=false
if ($LASTEXITCODE -ne 0) { throw 'what-if failed' }
$base = Invoke-AzJson -Arguments (@('deployment', 'group', 'create', '-n', 'qgw-base') + $common + @('-p', 'deployApps=false', '--query', 'properties.outputs'))
$kv = $base.keyVaultName.value; $st = $base.storageAccount.value; $share = $base.fileShare.value
Write-Check PASS "Base deployed: Key Vault $kv, storage $st/$share"

# 3. Secrets (values go through temp files, never the command line or the repository).
function Set-SecretIfMissing([string]$name, [string]$file, [switch]$Overwrite) {
    $exists = Invoke-AzJson -Arguments @('keyvault', 'secret', 'show', '--vault-name', $kv, '-n', $name, '--query', 'id') -AllowFail
    if ($exists -and -not $Overwrite) { Write-Check INFO "Secret $name already set; left unchanged"; return }
    for ($i = 0; $i -lt 6; $i++) {   # RBAC role assignment can take a minute to propagate
        & az keyvault secret set --vault-name $kv -n $name --file $file --encoding utf-8 -o none 2>$null
        if ($LASTEXITCODE -eq 0) { Write-Check PASS "Secret $name stored"; return }
        Start-Sleep -Seconds 20
    }
    throw "Could not set secret $name (do you have Key Vault Secrets Officer on $kv?)"
}
$tmp = New-TemporaryFile
try {
    $bytes = New-Object byte[] 24; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    Set-Content -Path $tmp -Value ([BitConverter]::ToString($bytes) -replace '-', '').ToLower() -NoNewline -Encoding ascii
    Set-SecretIfMissing 'qgw-api-key' $tmp
    if ($EeKeyFile) { Set-SecretIfMissing 'ee-service-account-json' (Resolve-Path $EeKeyFile) -Overwrite }
    else { Set-Content -Path $tmp -Value 'not-configured' -NoNewline -Encoding ascii; Set-SecretIfMissing 'ee-service-account-json' $tmp }
} finally { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }

# 4. Seed the share with the current local data, model registry and reports.
foreach ($pair in @(@('data/raw', 'data/raw'), @('data/processed', 'data/processed'), @('artifacts/real', 'artifacts/real'), @('reports/real', 'reports/real'))) {
    $src = Join-Path $root $pair[0]
    if (Test-Path $src) {
        & az storage file upload-batch --account-name $st --destination $share --destination-path $pair[1] --source $src --auth-mode key -o none
        if ($LASTEXITCODE -ne 0) { throw "Upload of $($pair[0]) failed" }
        Write-Check PASS "Uploaded $($pair[0]) to $share/$($pair[1])"
    }
}
if ($BaseOnly) { Write-Check PASS 'Base-only deployment finished (no apps).'; exit 0 }

# 5. Apps, jobs and alerts.
$apps = Invoke-AzJson -Arguments (@('deployment', 'group', 'create', '-n', 'qgw-apps') + $common + @('-p', 'deployApps=true', "imageTag=$ImageTag", '--query', 'properties.outputs'))
$api = $apps.apiUrl.value; $dash = $apps.dashboardUrl.value
Write-Check PASS "Apps deployed: API $api, dashboard $dash"

# 6. Verify (first request cold-starts the app; allow a few minutes).
& "$PSScriptRoot/verify.ps1" -ResourceGroup $ResourceGroup
exit $LASTEXITCODE
