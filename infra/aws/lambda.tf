# Log groups exist before the functions so their 7-day retention applies from the first log line.
resource "aws_cloudwatch_log_group" "fn" {
  for_each          = local.fn
  name              = "/aws/lambda/${each.value}"
  retention_in_days = var.log_retention_days
}

# --- API: slim image, Lambda Web Adapter -> uvicorn, public Function URL ------------------------
resource "aws_lambda_function" "api" {
  count         = local.compute
  function_name = local.fn.api
  role          = aws_iam_role.api.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.repo["api"].repository_url}:${var.api_image_tag}"
  architectures = ["x86_64"]
  memory_size   = var.api_memory_mb
  timeout       = 30

  environment {
    variables = {
      QGW_MODE          = "real"
      QGW_S3_BUCKET     = aws_s3_bucket.data.bucket
      QGW_S3_PULL       = "reports/real,data/processed/real"
      QGW_API_KEY_PARAM = local.ssm_api_key
      QGW_RATE_PER_MIN  = "60"
    }
  }

  lifecycle {
    # Images roll forward through CI / deploy.ps1 (aws lambda update-function-code); Terraform
    # only sets the first one, so an apply never rolls a newer image back.
    ignore_changes = [image_uri]
    precondition {
      condition     = var.api_image_tag != ""
      error_message = "Set api_image_tag (the git SHA pushed by the aws-deploy workflow) before create_compute = true."
    }
  }
  depends_on = [aws_cloudwatch_log_group.fn, aws_iam_role_policy_attachment.api_logs]
}

# authorization_type NONE: the app enforces its own optional X-API-Key (SSM /qgw/api-key) and
# rate limit. The provider adds the public invoke permissions.
resource "aws_lambda_function_url" "api" {
  count              = local.compute
  function_name      = aws_lambda_function.api[0].function_name
  authorization_type = "NONE"
  cors {
    allow_origins = ["*"]
    allow_methods = ["GET"]
    allow_headers = ["x-api-key", "content-type"]
    max_age       = 3600
  }
}

# --- Scheduled jobs: full image, awslambdaric -> src.aws_job.handler ---------------------------
resource "aws_lambda_function" "job" {
  for_each      = var.create_compute ? local.jobs : {}
  function_name = local.fn[each.key]
  role          = aws_iam_role.job.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.repo["app"].repository_url}:${var.app_image_tag}"
  architectures = ["x86_64"]
  memory_size   = var.job_memory_mb
  timeout       = 900

  ephemeral_storage {
    size = 2048
  }

  image_config {
    entry_point       = ["python", "-m", "awslambdaric"]
    command           = ["src.aws_job.handler"]
    working_directory = "/app"
  }

  environment {
    variables = {
      QGW_MODE                  = "real"
      QGW_S3_BUCKET             = aws_s3_bucket.data.bucket
      QGW_EE_KEY_PARAM          = local.ssm_ee_key
      HOME                      = "/tmp"
      MPLCONFIGDIR              = "/tmp/matplotlib"
      MLFLOW_DISABLE_AGENT_HINT = "1"
    }
  }

  lifecycle {
    ignore_changes = [image_uri]
    precondition {
      condition     = var.app_image_tag != ""
      error_message = "Set app_image_tag (the git SHA pushed by the aws-deploy workflow) before create_compute = true."
    }
  }
  depends_on = [aws_cloudwatch_log_group.fn, aws_iam_role_policy_attachment.job_logs]
}

# A failed weekly run is reported by the alarm; automatic retries would only repeat the cost.
resource "aws_lambda_function_event_invoke_config" "job" {
  for_each                     = aws_lambda_function.job
  function_name                = each.value.function_name
  maximum_retry_attempts       = 0
  maximum_event_age_in_seconds = 3600
}
