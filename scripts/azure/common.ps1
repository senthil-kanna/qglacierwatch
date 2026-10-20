# Shared helpers for the Azure scripts. Dot-source: . "$PSScriptRoot/common.ps1"
# Works in Windows PowerShell 5.1 and PowerShell 7. Calls the Azure CLI through the `az` command
# (tests replace it with a function to simulate Azure responses).

$ErrorActionPreference = 'Stop'
$script:ProjectTag = 'qglacierwatch'

function Invoke-AzJson {
    <# Run an az command with JSON output; returns parsed objects, or $null on failure when -AllowFail. #>
    param([Parameter(Mandatory)][string[]]$Arguments, [switch]$AllowFail)
    $out = & az @Arguments -o json 2>$null
    if ($LASTEXITCODE -ne 0) {
        if ($AllowFail) { return $null }
        throw "az $($Arguments -join ' ') failed (exit $LASTEXITCODE)"
    }
    $text = ($out -join "`n").Trim()
    if (-not $text) { return $null }
    # Windows PowerShell 5.1 emits a JSON array as ONE object; enumerate it so callers' @(...)
    # and Where-Object see individual items (otherwise per-resource tag checks silently pass).
    return $text | ConvertFrom-Json | ForEach-Object { $_ }
}

function Assert-AzCli {
    if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
        $default = 'C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin'
        if (Test-Path "$default\az.cmd") { $env:PATH = "$default;$env:PATH" }
        else { throw 'Azure CLI not found. Install: winget install -e --id Microsoft.AzureCLI' }
    }
}

function Get-CurrentAccount {
    $acct = Invoke-AzJson -Arguments @('account', 'show') -AllowFail
    if (-not $acct) { throw "Not logged in. Run: az login   (then re-run this script)" }
    return $acct
}

function Write-Check {
    param([ValidateSet('PASS', 'WARN', 'FAIL', 'INFO')][string]$Status, [string]$Message)
    $color = @{ PASS = 'Green'; WARN = 'Yellow'; FAIL = 'Red'; INFO = 'Gray' }[$Status]
    Write-Host ("[{0}] {1}" -f $Status, $Message) -ForegroundColor $color
}
