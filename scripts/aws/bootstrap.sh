#!/usr/bin/env bash
# One-time AWS setup for macOS/Linux/WSL; same steps as bootstrap.ps1 (the Windows script is the
# primary one and also offers to set an API key). Asks before creating anything.
#   ./scripts/aws/bootstrap.sh you@example.com
set -euo pipefail
EMAIL="${1:?usage: bootstrap.sh <alert-email>}"
PROJECT=qglacierwatch
REGION=ap-southeast-2   # the project's selected Region; the managed SCP denies all others
TF_DIR="$(cd "$(dirname "$0")/../../infra/aws" && pwd)"
aws() { command aws --region "$REGION" "$@"; }

for t in aws terraform; do command -v "$t" >/dev/null || { echo "missing tool: $t"; exit 1; }; done
ACCOUNT=$(aws sts get-caller-identity --query Account --output text) || { echo "Not signed in: run aws login --region $REGION --profile qgw; export AWS_PROFILE=qgw"; exit 1; }
echo "Account: $ACCOUNT  Region: $REGION  Project: $PROJECT"

fail=0
check() { if aws "${@:2}" >/dev/null 2>&1; then echo "[PASS] $1"; else echo "[FAIL] $1"; fail=1; fi; }
check S3 s3api list-buckets --max-items 1
check ECR ecr describe-repositories --max-items 1
check Lambda lambda list-functions --max-items 1
check ECS ecs list-clusters --max-items 1
check Scheduler scheduler list-schedules --max-results 1
check Logs logs describe-log-groups --limit 1
check SSM ssm describe-parameters --max-results 1
check IAM iam list-users --max-items 1
check Budgets budgets describe-budgets --account-id "$ACCOUNT" --max-results 1
[ "$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'length(Vpcs)' --output text)" -ge 1 ] \
  && echo "[PASS] default VPC" || { echo "[FAIL] no default VPC (aws ec2 create-default-vpc)"; fail=1; }
[ "$fail" = 0 ] || exit 1

if [ ! -f "$TF_DIR/terraform.tfvars" ]; then
  printf 'alert_email = "%s"\ncreate_compute = false\n' "$EMAIL" > "$TF_DIR/terraform.tfvars"
fi
terraform -chdir="$TF_DIR" init -input=false
terraform -chdir="$TF_DIR" plan -input=false -out=tfplan
read -r -p "Type yes to create the base resources shown above: " ok
[ "$ok" = yes ] || { echo "Stopped."; exit 2; }
terraform -chdir="$TF_DIR" apply -input=false tfplan; rm -f "$TF_DIR/tfplan"
mkdir -p "$HOME/qglacierwatch-tfstate-backups"
cp "$TF_DIR/terraform.tfstate" "$HOME/qglacierwatch-tfstate-backups/terraform.tfstate.$(date +%Y%m%d-%H%M%S)"

for p in /qgw/api-key /qgw/ee-service-account-json; do
  aws ssm get-parameter --name "$p" >/dev/null 2>&1 && echo "[PASS] $p exists" || {
    aws ssm put-parameter --name "$p" --type SecureString --value not-configured --tags "Key=project,Value=$PROJECT" >/dev/null
    echo "[PASS] $p created (placeholder)"; }
done
echo "Next: confirm the SNS e-mail, run seed-data, then:"
echo "  ./scripts/aws/github-keys.ps1   (stores the deploy user's key as GitHub secrets; Windows PowerShell or pwsh)"
