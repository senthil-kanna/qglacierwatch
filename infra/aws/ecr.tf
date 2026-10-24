# api: slim image for the API Lambda (docker/Dockerfile.api).
# app: full image for the dashboard (ECS) and the scheduled jobs (Lambda) (docker/Dockerfile).
# Tags: the git SHA, plus the mutable "live" tag on app that the dashboard task runs.

resource "aws_ecr_repository" "repo" {
  for_each             = toset(["api", "app"])
  name                 = "${var.project}-${each.key}"
  image_tag_mutability = "MUTABLE"
  force_delete         = true # images are rebuilt by CI; destroy should not get stuck on them
  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "repo" {
  for_each   = aws_ecr_repository.repo
  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "keep the 3 newest images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 3 }
      action       = { type = "expire" }
    }]
  })
}
