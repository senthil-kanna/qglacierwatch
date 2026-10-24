# QGlacierWatch on AWS: API on Lambda (Function URL), dashboard on one Fargate task with a public
# IP, weekly jobs on Lambda + EventBridge Scheduler, everything else in one S3 bucket.
# Deliberately absent: load balancers, NAT gateways, Elastic IPs, databases (tests/test_aws_infra.py).

data "aws_caller_identity" "me" {}
data "aws_partition" "p" {}

locals {
  tags = {
    project    = var.project
    managed-by = "terraform"
  }
  account = data.aws_caller_identity.me.account_id
  compute = var.create_compute ? 1 : 0
  bucket  = "${var.project}-${local.account}-${var.region}"

  # SSM SecureStrings are created (placeholder) and filled by scripts/aws/bootstrap.ps1, never by
  # Terraform, so their values stay out of the state file.
  ssm_api_key = "/qgw/api-key"
  ssm_ee_key  = "/qgw/ee-service-account-json"
  ssm_prefix  = "arn:${data.aws_partition.p.partition}:ssm:${var.region}:${local.account}:parameter"

  fn = {
    api     = "${var.project}-api"
    refresh = "${var.project}-refresh"
    drift   = "${var.project}-drift"
  }
  jobs = {
    refresh = var.refresh_schedule
    drift   = var.drift_schedule
  }
}
