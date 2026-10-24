<#
.SYNOPSIS
  Read-only checks before deploying QGlacierWatch to Azure. Creates nothing.

.DESCRIPTION
  Checks: Azure CLI and login, subscription state and offer, allowed regions (subscription policy
  and Container Apps availability), resource-provider registration, Container Apps and storage
  quotas, deployment permissions (resource groups + role assignments), Bicep compilation, and,
  with -ImageTag, that the GHCR image exists and is publicly pullable.
  -RegisterProviders registers missing providers (free, but it changes subscription settings).
  Exit code 1 if any check FAILs.

.EXAMPLE
  ./scripts/azure/preflight.ps1 -Location centralindia -ImageTag <git-sha>
#>
param(
    [string]$Location = 'centralindia',
    [string]$ResourceGroup = 'rg-qglacierwatch',
    [string]$Image = 'ghcr.io/senthil-kanna/qglacierwatch',
    [string]$ImageTag = '',
    [switch]$RegisterProviders
)

. "$PSScriptRoot/common.ps1"
$fails = 0
function Fail([string]$m) { Write-Check FAIL $m; $script:fails++ }

Assert-AzCli
$acct = Get-CurrentAccount
Write-Check INFO "Subscription: $($acct.name) ($($acct.id)), tenant $($acct.tenantId), user $($acct.user.name)"

# 1. Subscription state and offer
if ($acct.state -eq 'Enabled') { Write-Check PASS "Subscription state: Enabled" }
else { Fail "Subscription state is '$($acct.state)' (must be Enabled; student verification may still be pending)" }
$sub = Invoke-AzJson -Arguments @('rest', '--method', 'get', '--url', "https://management.azure.com/subscriptions/$($acct.id)?api-version=2022-12-01") -AllowFail
if ($sub) {
    $quotaId = $sub.subscriptionPolicies.quotaId
    $spending = $sub.subscriptionPolicies.spendingLimit
    if ($quotaId -match 'Student') { Write-Check PASS "Offer: $quotaId (spending limit: $spending)" }
    else { Write-Check WARN "Offer quotaId is '$quotaId', not an Azure for Students offer; costs may be billed to a card (spending limit: $spending)" }
}

# 2. Region: exists, allowed by policy, and offers Container Apps
$loc = Invoke-AzJson -Arguments @('account', 'list-locations', '--query', "[?name=='$Location'] | [0]")
if (-not $loc) { Fail "Region '$Location' is not available to this subscription" }
else {
    Write-Check PASS "Region exists: $($loc.displayName)"
    $assignments = Invoke-AzJson -Arguments @('policy', 'assignment', 'list') -AllowFail
    $allowed = @()
    foreach ($a in @($assignments)) {
        $p = $a.parameters
        if ($p -and $p.listOfAllowedLocations) { $allowed += $p.listOfAllowedLocations.value }
    }
    if ($allowed.Count -eq 0) { Write-Check INFO "No allowed-locations policy found on the subscription" }
    elseif ($allowed -contains $Location) { Write-Check PASS "Policy allows $Location (allowed: $($allowed -join ', '))" }
    else { Fail "Policy does not allow $Location. Allowed regions: $($allowed -join ', ')" }
    $acaLocs = Invoke-AzJson -Arguments @('provider', 'show', '-n', 'Microsoft.App', '--query', "resourceTypes[?resourceType=='managedEnvironments'].locations | [0]") -AllowFail
    if ($acaLocs -and ($acaLocs -contains $loc.displayName)) { Write-Check PASS "Container Apps available in $($loc.displayName)" }
    elseif ($acaLocs) { Fail "Container Apps not offered in $($loc.displayName)" }
    else { Write-Check WARN "Could not read Container Apps regions (provider not registered yet?)" }
}

# 3. Resource providers
$providers = 'Microsoft.App', 'Microsoft.OperationalInsights', 'Microsoft.Storage', 'Microsoft.KeyVault',
             'Microsoft.ManagedIdentity', 'Microsoft.Insights', 'Microsoft.Consumption'
foreach ($p in $providers) {
    $state = (Invoke-AzJson -Arguments @('provider', 'show', '-n', $p, '--query', '{s:registrationState}') -AllowFail).s
    if ($state -eq 'Registered') { Write-Check PASS "Provider $p registered" }
    elseif ($RegisterProviders) {
        & az provider register -n $p --wait | Out-Null
        if ($LASTEXITCODE -eq 0) { Write-Check PASS "Provider $p registered now" } else { Fail "Could not register $p" }
    }
    else { Fail "Provider $p is '$state'. Re-run with -RegisterProviders (free) or: az provider register -n $p" }
}

# 4. Quotas
$usages = Invoke-AzJson -Arguments @('rest', '--method', 'get', '--url', "https://management.azure.com/subscriptions/$($acct.id)/providers/Microsoft.App/locations/$Location/usages?api-version=2024-03-01") -AllowFail
if ($usages) {
    foreach ($u in $usages.value) {
        $free = $u.limit - $u.currentValue
        $msg = "Container Apps quota $($u.name.value): $($u.currentValue)/$($u.limit) used"
        if ($u.name.value -match 'ManagedEnvironmentCount' -and $free -lt 1) { Fail "$msg (need 1 free)" } else { Write-Check INFO $msg }
    }
} else { Write-Check WARN "Could not read Container Apps quotas (register Microsoft.App first)" }
$st = Invoke-AzJson -Arguments @('storage', 'account', 'show-usage', '-l', $Location) -AllowFail
if ($st) {
    if ($st.limit - $st.currentValue -ge 1) { Write-Check PASS "Storage accounts: $($st.currentValue)/$($st.limit) used" }
    else { Fail "Storage account quota exhausted in $Location" }
}

# 5. Permissions: create resource groups/resources and role assignments (managed identity -> Key Vault)
$perm = Invoke-AzJson -Arguments @('rest', '--method', 'get', '--url', "https://management.azure.com/subscriptions/$($acct.id)/providers/Microsoft.Authorization/permissions?api-version=2022-04-01") -AllowFail
function Test-Allowed($perms, [string]$action) {
    foreach ($p in @($perms.value)) {
        $hit = @($p.actions) | Where-Object { $action -like $_ }
        $deny = @($p.notActions) | Where-Object { $action -like $_ }
        if ($hit -and -not $deny) { return $true }
    }
    return $false
}
if ($perm) {
    foreach ($a in 'Microsoft.Resources/subscriptions/resourceGroups/write', 'Microsoft.Authorization/roleAssignments/write', 'Microsoft.App/containerApps/write') {
        if (Test-Allowed $perm $a) { Write-Check PASS "Permission: $a" } else { Fail "Missing permission: $a (need Owner, or Contributor + User Access Administrator)" }
    }
} else { Write-Check WARN "Could not read permissions" }
$oid = (& az ad signed-in-user show --query id -o tsv 2>$null)
if ($LASTEXITCODE -eq 0 -and $oid) { Write-Check PASS "Signed-in object id (for adminPrincipalId): $oid" }
else { Write-Check WARN "Could not read your object id; Key Vault secrets must then be set by an Owner" }

# 6. Template compiles
& az bicep build --file "$PSScriptRoot/../../infra/azure/main.bicep" --stdout *> $null
if ($LASTEXITCODE -eq 0) { Write-Check PASS "infra/azure/main.bicep compiles" } else { Fail "infra/azure/main.bicep does not compile (run: az bicep build --file infra/azure/main.bicep)" }

# 7. Existing resource group (informational; deploy is idempotent)
$rg = Invoke-AzJson -Arguments @('group', 'show', '-n', $ResourceGroup) -AllowFail
if ($rg) { Write-Check INFO "Resource group $ResourceGroup exists in $($rg.location) (tags: $(($rg.tags | ConvertTo-Json -Compress)))" }
else { Write-Check INFO "Resource group $ResourceGroup does not exist yet (deploy.ps1 creates it)" }

# 8. Image is public and the tag exists (Container Apps pulls GHCR anonymously)
if ($ImageTag) {
    $repo = $Image -replace '^ghcr\.io/', ''
    try {
        $tok = (Invoke-RestMethod "https://ghcr.io/token?scope=repository:${repo}:pull").token
        $h = @{ Authorization = "Bearer $tok"; Accept = 'application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json' }
        Invoke-WebRequest -Method Head -Uri "https://ghcr.io/v2/$repo/manifests/$ImageTag" -Headers $h -UseBasicParsing | Out-Null
        Write-Check PASS "Image ${Image}:$ImageTag exists and is publicly pullable"
    } catch {
        Fail "Image ${Image}:$ImageTag not pullable anonymously (not pushed yet, or package still private: GitHub > Packages > qglacierwatch > Package settings > Change visibility > Public)"
    }
} else { Write-Check INFO "Image not checked (pass -ImageTag <git-sha> from the 'image' workflow)" }

Write-Host ''
if ($fails -gt 0) { Write-Check FAIL "$fails check(s) failed; fix them before deploying."; exit 1 }
Write-Check PASS 'All pre-flight checks passed. Nothing was created.'
exit 0
