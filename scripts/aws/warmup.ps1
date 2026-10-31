<#
.SYNOPSIS
  Warm the API before a demo: /health, then keyed /v1/forecast calls, each timed. Read-only.

.DESCRIPTION
  The first /v1/forecast on a new Lambda container loads the 30 MB model bundle (about 25 s). This
  script pays that cost so the next requests answer in about half a second. The API key is read
  from SSM (/qgw/api-key) and only sent in the X-API-Key header; it is never printed.
  Lambda recycles containers that sit idle, and two requests at the same moment start a second
  cold container, so run this shortly before the demo (and again after a long idle gap).

.EXAMPLE
  ./scripts/aws/warmup.ps1
#>
param([ValidateRange(1, 5)][int]$Calls = 2)

. "$PSScriptRoot/common.ps1"
Assert-Tools
$null = Get-Identity

$api = Get-ApiUrl
if (-not $api) { throw 'API not deployed yet (run ./scripts/aws/deploy.ps1 -ImageTag <sha>)' }
$param = Invoke-Aws -Arguments @('ssm', 'get-parameter', '--name', '/qgw/api-key', '--with-decryption') -AllowFail
$headers = @{}
if ($param -and $param.Parameter.Value -and $param.Parameter.Value -ne $script:Placeholder) { $headers['X-API-Key'] = $param.Parameter.Value }
else { Write-Check WARN 'No API key in SSM (/qgw/api-key); calling /v1/forecast without one' }
$param = $null

function Measure-Get {
    param([string]$Path, [hashtable]$Headers = @{})
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try {
        $r = Invoke-RestMethod -Uri "$api$Path" -Headers $Headers -TimeoutSec 90
        Write-Check PASS ("GET /{0} in {1:N1} s" -f $Path, $sw.Elapsed.TotalSeconds)
        return $r
    }
    catch {
        Write-Check FAIL ("GET /{0} failed after {1:N1} s: {2}" -f $Path, $sw.Elapsed.TotalSeconds, $_.Exception.Message)
        return $null
    }
}

$ok = [bool](Measure-Get 'health')
foreach ($i in 1..$Calls) { $ok = [bool](Measure-Get 'v1/forecast' $headers) -and $ok }
$headers = $null
if (-not $ok) { Write-Check FAIL 'API not warm; check /aws/lambda/qglacierwatch-api in CloudWatch'; exit 1 }
Write-Banner "API warm: $api" 'Green'
exit 0
