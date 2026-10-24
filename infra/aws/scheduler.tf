resource "aws_scheduler_schedule" "job" {
  for_each                     = aws_lambda_function.job
  name                         = "${var.project}-${each.key}"
  schedule_expression          = local.jobs[each.key]
  schedule_expression_timezone = var.timezone
  state                        = var.schedules_enabled ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = each.value.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ job = each.key })
    retry_policy {
      maximum_retry_attempts = 0
    }
  }
}
