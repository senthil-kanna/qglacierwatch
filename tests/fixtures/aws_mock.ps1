# Fake AWS CLI and Terraform for script tests (same rule format as az_mock.ps1). Rules come from
# the JSON file in $env:AWS_MOCK_RULES: [{"match": "<regex on 'aws|terraform <args>'>", "out":
# "<stdout>", "exit": <code>}]; the first match wins, no match returns exit 1. Every call is
# appended to $env:AWS_MOCK_LOG. Functions take precedence over executables in PowerShell.
$global:AwsRules = Get-Content $env:AWS_MOCK_RULES -Raw | ConvertFrom-Json
function global:Invoke-MockCli {
    param([string]$Line)
    Add-Content -Path $env:AWS_MOCK_LOG -Value $Line
    foreach ($r in $global:AwsRules) {
        if ($Line -match $r.match) {
            $global:LASTEXITCODE = [int]$r.exit
            if ($r.out) { return $r.out }
            return
        }
    }
    $global:LASTEXITCODE = 1
}
function global:aws { Invoke-MockCli ("aws " + ($args -join ' ')) }
function global:terraform { Invoke-MockCli ("terraform " + ($args -join ' ')) }
# No real HTTP from tests: /health and the Streamlit health check answer as if healthy. API calls
# are logged as "http GET <uri> headers=<names>" (header values are never logged).
function global:Invoke-RestMethod {
    param([string]$Uri, [hashtable]$Headers = @{}, [int]$TimeoutSec)
    Add-Content -Path $env:AWS_MOCK_LOG -Value ("http GET $Uri headers=" + (@($Headers.Keys) -join ','))
    [pscustomobject]@{ status = 'ok'; model_id = 'gbm-test'; model_status = 'unpromoted_candidate'; problems = @() }
}
function global:Invoke-WebRequest { [pscustomobject]@{ StatusCode = 200 } }
