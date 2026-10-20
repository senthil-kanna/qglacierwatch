<#
.SYNOPSIS
  Delete the QGlacierWatch resource group, and nothing else.

.DESCRIPTION
  Safety rules (any failure aborts before deleting):
    - shows the active subscription, tenant, resource group, region and every resource in it
    - optional -SubscriptionId must match the active subscription
    - the resource group must carry tag project=qglacierwatch
    - EVERY resource in the group must carry that tag; an untagged (possibly unrelated) resource
      aborts the cleanup, so nothing outside this project is ever deleted
    - you must type the resource group name exactly (or pass it as -ConfirmName)
  -DryRun prints what would be deleted and exits.
  Key Vault is soft-deleted (7 days, no charge); -PurgeKeyVault purges only this project's vault.
  Not touched: Entra app registrations / federated credentials for GitHub OIDC (delete by hand).

.EXAMPLE
  ./scripts/azure/cleanup.ps1 -DryRun
  ./scripts/azure/cleanup.ps1 -ResourceGroup rg-qglacierwatch
#>
param(
    [string]$ResourceGroup = 'rg-qglacierwatch',
    [string]$SubscriptionId = '',
    [switch]$DryRun,
    [switch]$PurgeKeyVault,
    [string]$ConfirmName = ''
)

. "$PSScriptRoot/common.ps1"
Assert-AzCli
$acct = Get-CurrentAccount

Write-Host '=== Cleanup target ===' -ForegroundColor Cyan
Write-Host "Subscription : $($acct.name) ($($acct.id))"
Write-Host "Tenant       : $($acct.tenantId)"
Write-Host "Resource grp : $ResourceGroup"
if ($SubscriptionId -and $SubscriptionId -ne $acct.id) {
    Write-Check FAIL "Active subscription $($acct.id) is not the expected $SubscriptionId. Run: az account set -s $SubscriptionId"
    exit 1
}

$rg = Invoke-AzJson -Arguments @('group', 'show', '-n', $ResourceGroup) -AllowFail
if (-not $rg) { Write-Check INFO "Resource group $ResourceGroup does not exist; nothing to delete."; exit 0 }
Write-Host "Region       : $($rg.location)"
if ($rg.tags.project -ne $ProjectTag) {
    Write-Check FAIL "Resource group $ResourceGroup lacks tag project=$ProjectTag; it was not created by this project. Aborting."
    exit 1
}

$resources = @(Invoke-AzJson -Arguments @('resource', 'list', '-g', $ResourceGroup))
$foreign = @($resources | Where-Object { -not $_.tags -or $_.tags.project -ne $ProjectTag })
Write-Host "Resources    : $($resources.Count)"
foreach ($r in $resources) { Write-Host ("  - {0}  ({1})" -f $r.name, $r.type) }
if ($foreign.Count -gt 0) {
    Write-Check FAIL "These resources lack tag project=$ProjectTag and may not belong to this project:"
    foreach ($r in $foreign) { Write-Host ("    ! {0}  ({1})" -f $r.name, $r.type) -ForegroundColor Red }
    Write-Check FAIL 'Aborting: move or delete them yourself, or tag them if they are ours.'
    exit 1
}

if ($DryRun) { Write-Check INFO "Dry run: would delete resource group $ResourceGroup and the $($resources.Count) resources above."; exit 0 }

$answer = if ($ConfirmName) { $ConfirmName } else { Read-Host "Type the resource group name ($ResourceGroup) to DELETE it permanently, anything else to cancel" }
if ($answer -ne $ResourceGroup) { Write-Check INFO 'Cancelled; nothing deleted.'; exit 2 }

$vaults = @($resources | Where-Object { $_.type -eq 'Microsoft.KeyVault/vaults' } | ForEach-Object { $_.name })
& az group delete -n $ResourceGroup --yes
if ($LASTEXITCODE -ne 0) { Write-Check FAIL "az group delete failed (exit $LASTEXITCODE)"; exit 1 }
Write-Check PASS "Deleted resource group $ResourceGroup"

if ($PurgeKeyVault) {
    foreach ($v in $vaults) {
        & az keyvault purge -n $v
        if ($LASTEXITCODE -eq 0) { Write-Check PASS "Purged soft-deleted Key Vault $v" } else { Write-Check WARN "Could not purge $v (it expires by itself after 7 days)" }
    }
} elseif ($vaults) { Write-Check INFO "Key Vault $($vaults -join ', ') is soft-deleted for 7 days (no charge); -PurgeKeyVault removes it now." }

$left = Invoke-AzJson -Arguments @('group', 'exists', '-n', $ResourceGroup) -AllowFail
if ($left -eq $true) { Write-Check WARN 'Resource group still reported as existing; check the portal.' }
Write-Check INFO 'Check Cost Management over the next 1-2 days for trailing charges.'
exit 0
