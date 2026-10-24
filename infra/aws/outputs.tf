output "api_url" {
  description = "Public API base URL (Lambda Function URL); try <api_url>health."
  value       = var.create_compute ? aws_lambda_function_url.api[0].function_url : null
}

output "dashboard_url_hint" {
  description = "The dashboard has no fixed address; status.ps1 / resume.ps1 print http://<task IP>:8501."
  value       = "run scripts/aws/status.ps1"
}

output "bucket" {
  value = aws_s3_bucket.data.bucket
}

output "ecr_api" {
  value = aws_ecr_repository.repo["api"].repository_url
}

output "ecr_app" {
  value = aws_ecr_repository.repo["app"].repository_url
}

output "github_deploy_user" {
  description = "CI deploy user; scripts/aws/github-keys.ps1 creates its access key and stores it as GitHub secrets."
  value       = aws_iam_user.github_deploy.name
}

output "ecs_cluster" {
  value = aws_ecs_cluster.main.name
}

output "ecs_service" {
  value = var.create_compute ? aws_ecs_service.dashboard[0].name : null
}

output "functions" {
  value = local.fn
}

output "ssm_parameters" {
  value = { api_key = local.ssm_api_key, ee_key = local.ssm_ee_key }
}
