data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "ecs_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

locals {
  basic_logs = "arn:${data.aws_partition.p.partition}:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
  s3_list = {
    sid       = "List"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data.arn]
  }
}

# --- API Lambda: read features/reports, read the API key ---------------------------------------
resource "aws_iam_role" "api" {
  name               = "${var.project}-api"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role_policy_attachment" "api_logs" {
  role       = aws_iam_role.api.name
  policy_arn = local.basic_logs
}

data "aws_iam_policy_document" "api" {
  statement {
    sid       = local.s3_list.sid
    actions   = local.s3_list.actions
    resources = local.s3_list.resources
  }
  statement {
    sid       = "ReadServingParts"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.data.arn}/reports/*", "${aws_s3_bucket.data.arn}/data/processed/*"]
  }
  statement {
    sid       = "ApiKey"
    actions   = ["ssm:GetParameter"]
    resources = ["${local.ssm_prefix}${local.ssm_api_key}"]
  }
}

resource "aws_iam_role_policy" "api" {
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api.json
}

# --- Job Lambdas: read/write the bucket, read the Earth Engine key -----------------------------
resource "aws_iam_role" "job" {
  name               = "${var.project}-job"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role_policy_attachment" "job_logs" {
  role       = aws_iam_role.job.name
  policy_arn = local.basic_logs
}

data "aws_iam_policy_document" "job" {
  statement {
    sid       = local.s3_list.sid
    actions   = local.s3_list.actions
    resources = local.s3_list.resources
  }
  statement {
    sid     = "ReadWriteRoots"
    actions = ["s3:GetObject", "s3:PutObject"]
    resources = [
      "${aws_s3_bucket.data.arn}/data/*",
      "${aws_s3_bucket.data.arn}/artifacts/*",
      "${aws_s3_bucket.data.arn}/reports/*",
    ]
  }
  statement {
    sid       = "EarthEngineKey"
    actions   = ["ssm:GetParameter"]
    resources = ["${local.ssm_prefix}${local.ssm_ee_key}"]
  }
  statement {
    sid       = "DriftAlert"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
  }
}

resource "aws_iam_role_policy" "job" {
  role   = aws_iam_role.job.id
  policy = data.aws_iam_policy_document.job.json
}

# --- Dashboard (ECS): execution role pulls the image and writes logs; task role reads S3 --------
resource "aws_iam_role" "ecs_exec" {
  name               = "${var.project}-ecs-exec"
  assume_role_policy = data.aws_iam_policy_document.ecs_trust.json
}

resource "aws_iam_role_policy_attachment" "ecs_exec" {
  role       = aws_iam_role.ecs_exec.name
  policy_arn = "arn:${data.aws_partition.p.partition}:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "dashboard" {
  name               = "${var.project}-dashboard"
  assume_role_policy = data.aws_iam_policy_document.ecs_trust.json
}

data "aws_iam_policy_document" "dashboard" {
  statement {
    sid       = local.s3_list.sid
    actions   = local.s3_list.actions
    resources = local.s3_list.resources
  }
  statement {
    sid       = "ReadRoots"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.data.arn}/*"]
  }
  statement {
    sid       = "UploadAlert"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
  }
}

resource "aws_iam_role_policy" "dashboard" {
  role   = aws_iam_role.dashboard.id
  policy = data.aws_iam_policy_document.dashboard.json
}

# --- EventBridge Scheduler: invoke the two job functions ---------------------------------------
data "aws_iam_policy_document" "scheduler_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.project}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_trust.json
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    actions = ["lambda:InvokeFunction"]
    resources = [for k in keys(local.jobs) :
    "arn:${data.aws_partition.p.partition}:lambda:${var.region}:${local.account}:function:${local.fn[k]}"]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

# --- GitHub Actions deploy user --------------------------------------------------------------
# The project's managed SCP denies iam:*Provider*, so GitHub OIDC is impossible here. CI signs in
# as this user instead. Its access key is created OUTSIDE Terraform (scripts/aws/github-keys.ps1)
# so the secret never lands in the state file; force_destroy lets `destroy` remove that key too.
resource "aws_iam_user" "github_deploy" {
  name          = "${var.project}-github-deploy"
  force_destroy = true
}

data "aws_iam_policy_document" "github_deploy" {
  statement {
    sid       = "EcrLogin"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  # Signed-in pulls of public.ecr.aws base images (the Lambda adapter): anonymous pulls from the
  # shared GitHub runner IPs hit "429 toomanyrequests: Data limit exceeded".
  statement {
    sid       = "EcrPublicPull"
    actions   = ["ecr-public:GetAuthorizationToken", "sts:GetServiceBearerToken"]
    resources = ["*"]
  }
  statement {
    sid = "EcrPush"
    actions = [
      "ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:CompleteLayerUpload",
      "ecr:DescribeImages", "ecr:GetDownloadUrlForLayer", "ecr:InitiateLayerUpload",
      "ecr:PutImage", "ecr:UploadLayerPart",
    ]
    resources = [for r in aws_ecr_repository.repo : r.arn]
  }
  statement {
    sid       = local.s3_list.sid
    actions   = local.s3_list.actions
    resources = local.s3_list.resources
  }
  statement {
    sid       = "ReadForBake"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.data.arn}/*"]
  }
  statement {
    sid = "RollFunctions"
    actions = [
      "lambda:GetFunction", "lambda:GetFunctionConfiguration", "lambda:GetFunctionUrlConfig",
      "lambda:UpdateFunctionCode",
    ]
    resources = [for k, v in local.fn :
    "arn:${data.aws_partition.p.partition}:lambda:${var.region}:${local.account}:function:${v}"]
  }
  statement {
    sid       = "RollDashboard"
    actions   = ["ecs:DescribeServices", "ecs:UpdateService"]
    resources = ["arn:${data.aws_partition.p.partition}:ecs:${var.region}:${local.account}:service/${var.project}/${var.project}-dashboard"]
  }
}

resource "aws_iam_user_policy" "github_deploy" {
  user   = aws_iam_user.github_deploy.name
  policy = data.aws_iam_policy_document.github_deploy.json
}
