# Dashboard: one Fargate task in the default VPC's public subnets with a public IPv4 address.
# Streamlit needs WebSockets, so it cannot sit behind a Lambda Function URL; a load balancer would
# cost ~USD 17/month, so there is none. The URL is http://<task public IP>:8501; the IP changes
# when the task restarts (resume.ps1 / status.ps1 print it).

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "public" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

resource "aws_cloudwatch_log_group" "dashboard" {
  name              = "/ecs/${var.project}-dashboard"
  retention_in_days = var.log_retention_days
}

resource "aws_security_group" "dashboard" {
  name        = "${var.project}-dashboard"
  description = "Streamlit dashboard on 8501"
  vpc_id      = data.aws_vpc.default.id
}

resource "aws_vpc_security_group_ingress_rule" "dashboard" {
  security_group_id = aws_security_group.dashboard.id
  description       = "dashboard"
  ip_protocol       = "tcp"
  from_port         = 8501
  to_port           = 8501
  cidr_ipv4         = var.dashboard_cidr
}

resource "aws_vpc_security_group_egress_rule" "dashboard" {
  security_group_id = aws_security_group.dashboard.id
  description       = "ECR, S3, CloudWatch over the internet gateway (no NAT)"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_ecs_cluster" "main" {
  name = var.project
  setting {
    name  = "containerInsights"
    value = "disabled" # extra CloudWatch cost; not needed for one task
  }
}

resource "aws_ecs_task_definition" "dashboard" {
  count                    = local.compute
  family                   = "${var.project}-dashboard"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.dashboard_cpu
  memory                   = var.dashboard_memory_mb
  execution_role_arn       = aws_iam_role.ecs_exec.arn
  task_role_arn            = aws_iam_role.dashboard.arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
  container_definitions = jsonencode([{
    name         = "dashboard"
    image        = "${aws_ecr_repository.repo["app"].repository_url}:live"
    command      = ["dashboard"]
    essential    = true
    portMappings = [{ containerPort = 8501, protocol = "tcp" }]
    environment = [
      { name = "QGW_MODE", value = "real" },
      { name = "QGW_S3_BUCKET", value = aws_s3_bucket.data.bucket },
      { name = "AWS_DEFAULT_REGION", value = var.region },
      { name = "QGW_ALERT_TOPIC_ARN", value = aws_sns_topic.alerts.arn },
      { name = "QGW_API_URL", value = aws_lambda_function_url.api[0].function_url },
    ]
    healthCheck = {
      command     = ["CMD-SHELL", "curl -fsS http://localhost:8501/_stcore/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 120
    }
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.dashboard.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "dashboard"
      }
    }
  }])
}

resource "aws_ecs_service" "dashboard" {
  count                  = local.compute
  name                   = "${var.project}-dashboard"
  cluster                = aws_ecs_cluster.main.id
  task_definition        = aws_ecs_task_definition.dashboard[0].arn
  desired_count          = var.dashboard_enabled ? 1 : 0
  launch_type            = "FARGATE"
  platform_version       = "LATEST"
  enable_execute_command = false
  # One task only: stop the old task before starting the new one (no double billing, no LB).
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  network_configuration {
    subnets          = data.aws_subnets.public.ids
    security_groups  = [aws_security_group.dashboard.id]
    assign_public_ip = true
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
}
