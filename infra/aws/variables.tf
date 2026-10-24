variable "project" {
  description = "Name prefix and value of the project tag."
  type        = string
  default     = "qglacierwatch"
}

variable "region" {
  description = "All resources live in one region: the project's selected Region (the managed SCP denies others)."
  type        = string
  default     = "ap-southeast-2"
}

variable "alert_email" {
  description = "Receives the budget alerts and the CloudWatch alarm e-mails (confirm the SNS subscription mail)."
  type        = string
}

variable "create_compute" {
  description = "false = base only (S3, ECR, IAM, budget) so images can be pushed first; true = Lambdas, ECS, schedules, alarms."
  type        = bool
  default     = false
}

variable "api_image_tag" {
  description = "Initial tag of the API image in ECR. Later rollouts update the functions directly (CI or deploy.ps1)."
  type        = string
  default     = ""
}

variable "app_image_tag" {
  description = "Initial tag of the full image (scheduled jobs). The dashboard always runs the mutable 'live' tag."
  type        = string
  default     = ""
}

variable "dashboard_enabled" {
  description = "Run the Fargate dashboard task (pause.ps1 sets false, resume.ps1 true)."
  type        = bool
  default     = true
}

variable "schedules_enabled" {
  description = "Enable the weekly refresh and drift schedules."
  type        = bool
  default     = true
}

variable "dashboard_cidr" {
  description = "Who may open the dashboard on port 8501."
  type        = string
  default     = "0.0.0.0/0"
}

variable "monthly_budget_usd" {
  description = "AWS Budgets monthly cost limit (alerts at 50/80/100 %)."
  type        = number
  default     = 20
}

variable "api_memory_mb" {
  type    = number
  default = 1024
}

variable "job_memory_mb" {
  description = "3008 MB is the largest size new accounts get by default."
  type        = number
  default     = 3008
}

variable "dashboard_cpu" {
  type    = number
  default = 512
}

variable "dashboard_memory_mb" {
  type    = number
  default = 1024
}

variable "log_retention_days" {
  type    = number
  default = 7
}

variable "timezone" {
  type    = string
  default = "Asia/Kolkata"
}

variable "refresh_schedule" {
  description = "Weekly refresh (ingest when an Earth Engine key is in SSM, else --skip-ingest), Monday 02:00."
  type        = string
  default     = "cron(0 2 ? * MON *)"
}

variable "drift_schedule" {
  description = "Weekly operational drift check, Monday 04:00."
  type        = string
  default     = "cron(0 4 ? * MON *)"
}
