<#
.SYNOPSIS
  One-time AWS setup: checks, base infrastructure, SSM placeholders. Asks before creating anything.

.DESCRIPTION
  1. Checks tools, sign-in, region and READ-ONLY access to every service the project uses
     (nothing is created by the checks).
  2. terraform init + plan/apply with create_compute=false: S3 bucket, 2 ECR repositories, IAM roles,
     GitHub OIDC provider + deploy role, ECS cluster, security group, log group, SNS topic, budget.
     None of these costs money while empty/idle (S3/ECR bill only for stored bytes).
  3. Creates the SSM SecureStrings /qgw/api-key and /qgw/ee-service-account-json with the
     placeholder "not-configured" (open API, --skip-ingest refresh). Optionally sets an API key
     (typed hidden, never shown or logged).
  4. Prints the next commands.

.EXAMPLE
  ./scripts/aws/bootstrap.ps1 -AlertEmail you@example.com
#>
param(
    [Parameter(Mandatory)][string]$AlertEmail,
    [switch]$CheckOnly,
    [switch]$Yes
)

. "$PSScriptRoot/common.ps1"
Assert-Tools
$id = Get-Identity
Show-Target $id

Write-Host "`n=== Read-only access checks ===" -ForegroundColor Cyan
$checks = [ordered]@{
    'S3'                   = @('s3api', 'list-buckets', '--max-items', '1')
    'ECR'                  = @('ecr', 'describe-repositories', '--max-items', '1')
    'Lambda'               = @('lambda', 'list-functions', '--max-items', '1')
    'ECS'                  = @('ecs', 'list-clusters', '--max-items', '1')
    'EventBridge Scheduler' = @('scheduler', 'list-schedules', '--max-results', '1')
    'CloudWatch Logs'      = @('logs', 'describe-log-groups', '--limit', '1')
    'CloudWatch alarms'    = @('cloudwatch', 'describe-alarms', '--max-records', '1')
    'SNS'                  = @('sns', 'list-topics')
    'SSM Parameter Store'  = @('ssm', 'describe-parameters', '--max-results', '1')
    'IAM'                  = @('iam', 'list-open-id-connect-providers')
    'Budgets'              = @('budgets', 'describe-budgets', '--account-id', $id.Account, '--max-results', '1')
}
$failed = 0
foreach ($name in $checks.Keys) {
    $r = Invoke-Aws -Arguments $checks[$name] -Raw -AllowFail
    if ($null -eq $r) { Write-Check FAIL "$name not accessible (Free plan restriction or missing permission)"; $failed++ }
    else { Write-Check PASS $name }
}
$vpc = Invoke-Aws -Arguments @('ec2', 'describe-vpcs', '--filters', 'Name=isDefault,Values=true') -AllowFail
if ($vpc -and @($vpc.Vpcs).Count -ge 1) { Write-Check PASS "Default VPC $(@($vpc.Vpcs)[0].VpcId) (dashboard runs in its public subnets)" }
else { Write-Check FAIL 'No default VPC in ap-south-1. Create one: aws ec2 create-default-vpc --region ap-south-1'; $failed++ }
if ($failed) { Write-Check FAIL "$failed check(s) failed; fix them before continuing."; exit 1 }
if ($CheckOnly) { Write-Check INFO 'Checks only (-CheckOnly). Nothing was created.'; exit 0 }

Write-Host "`n=== Base infrastructure (Terraform, local state in infra/aws) ===" -ForegroundColor Cyan
$vars = Read-TfVars
if (-not $vars.Contains('create_compute')) { $vars['create_compute'] = 'false' }
Set-TfVars @{ alert_email = $AlertEmail; create_compute = $vars['create_compute'] }
Write-Host 'Commands that will run:'
Write-Host '  terraform -chdir=infra/aws init'
Write-Host '  terraform -chdir=infra/aws plan -out=tfplan      (shows every resource first)'
Write-Host '  terraform -chdir=infra/aws apply tfplan          (only after you type yes)'
Invoke-Terraform -Arguments @('init', '-input=false')
Invoke-TfApply -Why 'create the base resources (no Lambdas, no Fargate yet)' -Yes:$Yes

Write-Host "`n=== SSM parameters (values never pass through Terraform) ===" -ForegroundColor Cyan
foreach ($p in $script:SsmParams) {
    $exists = Invoke-Aws -Arguments @('ssm', 'get-parameter', '--name', $p) -AllowFail
    if ($exists) { Write-Check PASS "$p exists (value unchanged)"; continue }
    Invoke-Aws -Arguments @('ssm', 'put-parameter', '--name', $p, '--type', 'SecureString', '--value', $script:Placeholder,
        '--tags', "Key=project,Value=$script:Project") | Out-Null
    Write-Check PASS "$p created with placeholder '$script:Placeholder'"
}
if (-not $Yes) {
    $set = Read-Host 'Require an API key on /v1 routes now? (y/N; the demo works without one)'
    if ($set -eq 'y') {
        $secure = Read-Host 'API key (hidden)' -AsSecureString
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
        $tmp = New-TemporaryFile
        try {
            [IO.File]::WriteAllText($tmp.FullName, $plain)
            Invoke-Aws -Arguments @('ssm', 'put-parameter', '--name', '/qgw/api-key', '--type', 'SecureString', '--overwrite',
                '--value', "file://$($tmp.FullName)") | Out-Null
            Write-Check PASS 'API key stored in SSM /qgw/api-key (clients send it as X-API-Key)'
        }
        finally { Remove-Item $tmp.FullName -Force; $plain = $null }
    }
}

$role = Get-TfOutput 'github_deploy_role_arn'
Write-Banner 'Bootstrap done. Next steps:' 'Cyan'
Write-Host "1. Confirm the SNS subscription e-mail AWS just sent to $AlertEmail."
Write-Host '2. Upload data, models and reports:   ./scripts/aws/seed-data.ps1'
Write-Host '3. Let GitHub deploy without keys (repository VARIABLE, not a secret):'
Write-Host "     gh variable set AWS_DEPLOY_ROLE_ARN --body $role"
Write-Host '4. Build and push the images:   gh workflow run ci.yml --ref feat/aws-deployment'
Write-Host '   (wait for the aws-deploy job; its summary shows the image tag = commit SHA)'
Write-Host '5. Create the API, jobs and dashboard:   ./scripts/aws/deploy.ps1 -ImageTag <sha>'
Write-Host "Keep a copy of $script:BackupDir; it holds the Terraform state backups."
