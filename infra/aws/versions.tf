# State is LOCAL (infra/aws/terraform.tfstate, git-ignored): no state bucket to bootstrap and
# `terraform destroy` works from the laptop. Back the file up after every apply
# (docs/aws-deployment.md); if it is lost, scripts/aws/destroy.ps1 -Orphans lists tagged leftovers.
terraform {
  required_version = ">= 1.16.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.70"
    }
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = local.tags
  }
}
