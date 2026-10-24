"""AWS deployment assets: cost guards on the Terraform, image/requirements consistency and the
deploy scripts' syntax. Nothing here contacts AWS."""

import os
import re
import shutil
import subprocess

import pytest

from src import config

ROOT = config.ROOT
TF_DIR = ROOT / "infra" / "aws"
TF = "\n".join(p.read_text(encoding="utf-8") for p in sorted(TF_DIR.glob("*.tf")))
TERRAFORM = os.getenv("TERRAFORM") or shutil.which("terraform")


def pins(path):
    out = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        m = re.match(r"\s*([A-Za-z0-9_.-]+)(\[[^\]]*\])?==(\S+)", line)
        if m:
            out[m.group(1).lower()] = m.group(3)
    return out


# --- cost guards ---------------------------------------------------------------------------------

@pytest.mark.parametrize("forbidden", [
    r'resource\s+"aws_(lb|alb|elb)"', r'resource\s+"aws_lb_', r'resource\s+"aws_nat_gateway"',
    r'resource\s+"aws_eip"', r"\bload_balancer\s*\{", r'resource\s+"aws_(db_instance|rds_cluster|dynamodb_table)"',
    r'resource\s+"aws_sagemaker_', r'resource\s+"aws_instance"', r"FARGATE_SPOT",
])
def test_no_costly_or_unneeded_resources(forbidden):
    assert not re.search(forbidden, TF), f"infra/aws must not contain {forbidden}"


def test_region_tags_and_log_retention():
    assert re.search(r'variable "region" \{[^}]*default\s*=\s*"ap-south-1"', TF)
    assert "default_tags" in TF and re.search(r"project\s*=\s*var\.project", TF)
    assert re.search(r'variable "log_retention_days" \{[^}]*default\s*=\s*7\b', TF)
    groups = re.findall(r'resource "aws_cloudwatch_log_group"[^{]*\{(.*?)\n\}', TF, re.S)
    assert groups and all("retention_in_days = var.log_retention_days" in g for g in groups)


def test_single_dashboard_task_with_public_ip_and_no_secrets_in_terraform():
    assert "assign_public_ip = true" in TF and "desired_count          = var.dashboard_enabled ? 1 : 0" in TF
    assert 'resource "aws_ssm_parameter"' not in TF, "SSM values would land in the state file; bootstrap.ps1 creates them"
    # Literal values only (parameter names like "/qgw/api-key" and interpolations are fine).
    assert not re.search(r"(?i)(secret|password|api_key)\s*=\s*\"[^\"$/][^\"]*\"", TF)


def test_budget_and_job_retries():
    assert re.search(r'variable "monthly_budget_usd" \{[^}]*default\s*=\s*20\b', TF)
    assert "for_each = [50, 80, 100]" in TF
    assert TF.count("maximum_retry_attempts") >= 2


@pytest.mark.skipif(TERRAFORM is None, reason="terraform not installed (set TERRAFORM=path to run)")
def test_terraform_fmt_and_validate(tmp_path):
    fmt = subprocess.run([TERRAFORM, "fmt", "-check", "-recursive", str(TF_DIR)], capture_output=True, text=True)
    assert fmt.returncode == 0, "run: terraform fmt -recursive infra/aws\n" + fmt.stdout
    if not (TF_DIR / ".terraform").exists():
        pytest.skip("run `terraform -chdir=infra/aws init -backend=false` first")
    val = subprocess.run([TERRAFORM, f"-chdir={TF_DIR}", "validate", "-no-color"], capture_output=True, text=True)
    assert val.returncode == 0, val.stdout + val.stderr


# --- images --------------------------------------------------------------------------------------

def test_api_requirements_are_a_pinned_subset():
    full, api = pins(ROOT / "requirements.txt"), pins(ROOT / "requirements-api.txt")
    assert {"fastapi", "lightgbm", "scikit-learn", "pandas", "boto3"} <= api.keys()
    assert not {"torch", "pennylane", "earthengine-api", "mlflow", "streamlit"} & api.keys()
    assert {k: v for k, v in api.items() if full.get(k) != v} == {}


def test_api_image_is_slim_non_root_and_pinned():
    d = (ROOT / "docker" / "Dockerfile.api").read_text(encoding="utf-8")
    assert re.search(r"aws-lambda-adapter:\d+\.\d+\.\d+ ", d), "pin the Lambda Web Adapter version"
    assert "requirements-api.txt" in d and "USER qgw" in d and "AWS_LWA_READINESS_CHECK_PATH=/health" in d
    assert "!build/api-bundle/**" in (ROOT / ".dockerignore").read_text(encoding="utf-8")


# --- CI/CD ---------------------------------------------------------------------------------------

def test_workflows_pin_third_party_actions_by_sha_and_store_no_aws_keys():
    for wf in (ROOT / ".github" / "workflows").glob("*.yml"):
        text = wf.read_text(encoding="utf-8")
        for ref in re.findall(r"uses:\s*([^\s#]+)", text):
            if not ref.startswith("actions/"):
                assert re.search(r"@[0-9a-f]{40}$", ref), f"{wf.name}: pin {ref} to a commit SHA"
        assert "AWS_SECRET_ACCESS_KEY" not in text and "aws-access-key-id" not in text
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25" in ci and "0.28.0 were removed" in ci
    assert "id-token: write" in ci and "environment:" not in ci.split("aws-deploy:")[1]
