# Fake Azure CLI for script tests. Replaces `az` with a function (functions take precedence over
# executables in PowerShell). Rules come from the JSON file in $env:AZ_MOCK_RULES: a list of
# {"match": "<regex on the joined arguments>", "out": "<stdout>", "exit": <code>}; the first match
# wins, no match returns exit 1. Every call is appended to $env:AZ_MOCK_LOG.
# $global: because `$script:` inside a function resolves to the *calling* script's scope.
$global:AzRules = Get-Content $env:AZ_MOCK_RULES -Raw | ConvertFrom-Json
function global:az {
    $line = $args -join ' '
    Add-Content -Path $env:AZ_MOCK_LOG -Value $line
    foreach ($r in $global:AzRules) {
        if ($line -match $r.match) {
            $global:LASTEXITCODE = [int]$r.exit
            if ($r.out) { return $r.out }
            return
        }
    }
    $global:LASTEXITCODE = 1
}
