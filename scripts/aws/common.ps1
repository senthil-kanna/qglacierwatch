# Shared helpers for the AWS scripts. Dot-source: . "$PSScriptRoot/common.ps1"
# Works in Windows PowerShell 5.1 and PowerShell 7. Calls the AWS CLI through the `aws` command and
# Terraform through `terraform` (tests replace both with functions to simulate responses).

$ErrorActionPreference = 'Stop'
$script:Project = 'qglacierwatch'
$script:Region = 'ap-southeast-2'  # the project's selected Region; the managed SCP denies all others
$script:RepoRoot = (Resolve-Path "$PSScriptRoot/../..").Path
$script:TfDir = if ($env:QGW_TF_DIR) { $env:QGW_TF_DIR } else { Join-Path $script:RepoRoot 'infra/aws' }  # tests override
$script:TfVars = Join-Path $script:TfDir 'terraform.tfvars'
$script:SsmParams = @('/qgw/api-key', '/qgw/ee-service-account-json')
$script:Placeholder = 'not-configured'
$script:BackupDir = if ($env:QGW_TFSTATE_BACKUPS) { $env:QGW_TFSTATE_BACKUPS } else { Join-Path $HOME 'qglacierwatch-tfstate-backups' }

function Write-Check {
    param([ValidateSet('PASS', 'WARN', 'FAIL', 'INFO')][string]$Status, [string]$Message)
    $color = @{ PASS = 'Green'; WARN = 'Yellow'; FAIL = 'Red'; INFO = 'Gray' }[$Status]
    Write-Host ("[{0}] {1}" -f $Status, $Message) -ForegroundColor $color
}

function Write-Banner {
    param([string]$Text, [string]$Color = 'Green')
    $line = '=' * ([Math]::Max(60, $Text.Length + 4))
    Write-Host ''
    Write-Host $line -ForegroundColor $Color
    Write-Host "  $Text" -ForegroundColor $Color
    Write-Host $line -ForegroundColor $Color
    Write-Host ''
}

function Invoke-Aws {
    <# Run an aws command with JSON output in the project region; returns parsed objects, or $null on
       failure when -AllowFail. stderr is suppressed (Windows PowerShell 5.1 would turn it into errors). #>
    param([Parameter(Mandatory)][string[]]$Arguments, [switch]$AllowFail, [switch]$Raw)
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $out = & aws @Arguments --region $script:Region --output json 2>$null; $code = $LASTEXITCODE }
    finally { $ErrorActionPreference = $old }
    if ($code -ne 0) {
        if ($AllowFail) { return $null }
        throw "aws $($Arguments -join ' ') failed (exit $code)"
    }
    $text = ($out -join "`n").Trim()
    if ($Raw) { return $text }
    if (-not $text) { return $null }
    return $text | ConvertFrom-Json
}

function Invoke-Terraform {
    <# terraform -chdir=infra/aws <args>, streaming output; throws on a non-zero exit. #>
    param([Parameter(Mandatory)][string[]]$Arguments)
    & terraform "-chdir=$script:TfDir" @Arguments
    if ($LASTEXITCODE -ne 0) { throw "terraform $($Arguments -join ' ') failed (exit $LASTEXITCODE)" }
}

function Get-TfOutput {
    param([Parameter(Mandatory)][string]$Name)
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $v = & terraform "-chdir=$script:TfDir" output -raw $Name 2>$null; $code = $LASTEXITCODE }
    finally { $ErrorActionPreference = $old }
    if ($code -ne 0) { return $null }
    return (($v -join '').Trim())
}

function Assert-Tools {
    $missing = @()
    if (-not (Get-Command aws -ErrorAction SilentlyContinue)) { $missing += 'AWS CLI v2:  winget install -e --id Amazon.AWSCLI' }
    if (-not (Get-Command terraform -ErrorAction SilentlyContinue)) { $missing += 'Terraform:   winget install -e --id Hashicorp.Terraform' }
    if ($missing) { throw ("Missing tools (install, then open a NEW terminal):`n  " + ($missing -join "`n  ")) }
}

function Get-Identity {
    $id = Invoke-Aws -Arguments @('sts', 'get-caller-identity') -AllowFail
    if (-not $id) { throw "Not signed in to AWS. Run: aws login --region $script:Region --profile qgw; `$env:AWS_PROFILE = 'qgw'; then re-run." }
    return $id
}

function Show-Target {
    param($Identity)
    Write-Host '=== AWS target ===' -ForegroundColor Cyan
    Write-Host "Account : $($Identity.Account)"
    Write-Host "Caller  : $($Identity.Arn)"
    Write-Host "Region  : $script:Region"
    Write-Host "Profile : $(if ($env:AWS_PROFILE) { $env:AWS_PROFILE } else { 'default (set $env:AWS_PROFILE to use another)' })"
    Write-Host "Project : $script:Project (every resource is tagged project=$script:Project)"
}

function Confirm-Step {
    <# Ask before anything that creates, changes or deletes resources. -Yes skips (for repeat runs). #>
    param([Parameter(Mandatory)][string]$Message, [switch]$Yes)
    Write-Host ''
    Write-Host $Message -ForegroundColor Yellow
    if ($Yes) { Write-Host '(-Yes given: continuing)'; return }
    $answer = Read-Host 'Type yes to continue'
    if ($answer -ne 'yes') { Write-Host 'Stopped. Nothing further was changed.'; exit 2 }
}

function Read-TfVars {
    $vars = [ordered]@{}
    if (Test-Path $script:TfVars) {
        foreach ($line in Get-Content $script:TfVars) {
            if ($line -match '^\s*([A-Za-z0-9_]+)\s*=\s*(.+?)\s*(#.*)?$') { $vars[$Matches[1]] = $Matches[2].Trim('"') }
        }
    }
    return $vars
}

function Set-TfVars {
    <# Merge values into infra/aws/terraform.tfvars (git-ignored). Booleans and numbers stay unquoted. #>
    param([Parameter(Mandatory)][hashtable]$Values)
    $vars = Read-TfVars
    foreach ($k in $Values.Keys) { $vars[$k] = [string]$Values[$k] }
    $lines = @('# Managed by scripts/aws/*.ps1 (git-ignored). See terraform.tfvars.example.')
    foreach ($k in $vars.Keys) {
        $v = $vars[$k]
        if ($v -match '^(true|false|-?\d+(\.\d+)?)$') { $lines += "$k = $v" } else { $lines += "$k = `"$v`"" }
    }
    Set-Content -Path $script:TfVars -Value $lines -Encoding ascii
}

function Backup-TfState {
    $state = Join-Path $script:TfDir 'terraform.tfstate'
    if (-not (Test-Path $state)) { return }
    New-Item -ItemType Directory -Force $script:BackupDir | Out-Null
    $dest = Join-Path $script:BackupDir ("terraform.tfstate.{0}" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    Copy-Item $state $dest
    Write-Check INFO "State backed up to $dest (also copy this folder somewhere safe, e.g. OneDrive)"
}

function Invoke-TfApply {
    <# plan -> show -> confirm -> apply the saved plan -> back up the state. #>
    param([string]$Why = 'apply the plan above', [switch]$Yes, [string[]]$Extra = @())
    $plan = Join-Path $script:TfDir 'tfplan'
    Invoke-Terraform -Arguments (@('plan', '-input=false', '-out=tfplan') + $Extra)
    Confirm-Step -Message "Terraform will $Why (see 'Plan:' line above for counts)." -Yes:$Yes
    try { Invoke-Terraform -Arguments @('apply', '-input=false', 'tfplan') }
    finally { Remove-Item $plan -ErrorAction SilentlyContinue; Backup-TfState }
}

function Get-DashboardUrl {
    <# http://<public ip>:8501 of the running dashboard task, or $null. #>
    $tasks = Invoke-Aws -Arguments @('ecs', 'list-tasks', '--cluster', $script:Project, '--service-name', "$script:Project-dashboard", '--desired-status', 'RUNNING') -AllowFail
    if (-not $tasks -or -not $tasks.taskArns) { return $null }
    $desc = Invoke-Aws -Arguments (@('ecs', 'describe-tasks', '--cluster', $script:Project, '--tasks') + @($tasks.taskArns)) -AllowFail
    foreach ($t in @($desc.tasks)) {
        if ($t.lastStatus -ne 'RUNNING') { continue }
        $eni = (@($t.attachments)[0].details | Where-Object { $_.name -eq 'networkInterfaceId' }).value
        if (-not $eni) { continue }
        $ni = Invoke-Aws -Arguments @('ec2', 'describe-network-interfaces', '--network-interface-ids', $eni) -AllowFail
        $ip = @($ni.NetworkInterfaces)[0].Association.PublicIp
        if ($ip) { return "http://${ip}:8501" }
    }
    return $null
}

function Get-ApiUrl {
    $cfg = Invoke-Aws -Arguments @('lambda', 'get-function-url-config', '--function-name', "$script:Project-api") -AllowFail
    if ($cfg) { return $cfg.FunctionUrl }
    return $null
}
