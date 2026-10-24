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


# --- deploy scripts (PowerShell, against tests/fixtures/aws_mock.ps1) ------------------------------

SCRIPTS = ROOT / "scripts" / "aws"
SHELL = shutil.which("pwsh") or shutil.which("powershell")
needs_ps = pytest.mark.skipif(SHELL is None, reason="PowerShell not available")
IDENT = {"Account": "111122223333", "Arn": "arn:aws:iam::111122223333:user/student", "UserId": "x"}


def mock(match, out=None, code=0):
    return {"match": match, "out": None if out is None else out if isinstance(out, str) else __import__("json").dumps(out), "exit": code}


def run_ps(tmp_path, script, args, rules):
    import json

    (tmp_path / "rules.json").write_text(json.dumps(rules))
    log = tmp_path / "cli.log"
    log.write_text("")
    tf = tmp_path / "tf"
    tf.mkdir(exist_ok=True)
    cmd = f". '{ROOT / 'tests' / 'fixtures' / 'aws_mock.ps1'}'; & '{SCRIPTS / script}' {args}; exit $LASTEXITCODE"
    env = {**os.environ, "AWS_MOCK_RULES": str(tmp_path / "rules.json"), "AWS_MOCK_LOG": str(log),
           "QGW_TF_DIR": str(tf), "QGW_TFSTATE_BACKUPS": str(tmp_path / "bak")}
    p = subprocess.run([SHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                       capture_output=True, text=True, env=env, timeout=120)
    return p.returncode, p.stdout + p.stderr, log.read_text().splitlines(), tf


@needs_ps
@pytest.mark.parametrize("script", sorted(p.name for p in SCRIPTS.glob("*.ps1")))
def test_aws_scripts_parse(script):
    cmd = (f"$e=$null; [System.Management.Automation.Language.Parser]::ParseFile('{SCRIPTS / script}', [ref]$null, [ref]$e) | Out-Null; "
           "if ($e.Count) { $e | % { $_.ToString() }; exit 1 }")
    p = subprocess.run([SHELL, "-NoProfile", "-NonInteractive", "-Command", cmd], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr


def destroy_rules():
    tagged = {"ResourceTagMappingList": [{"ResourceARN": "arn:aws:s3:::qglacierwatch-111122223333-ap-south-1"}]}
    return [mock(r"^aws sts get-caller-identity", IDENT), mock(r"^aws resourcegroupstaggingapi", tagged),
            mock(r"^terraform .*output -raw bucket", "qglacierwatch-111122223333-ap-south-1"),
            mock(r"^aws s3api list-object-versions", {"Versions": []}), mock(r"^aws s3api delete-objects", "{}"),
            mock(r"^terraform .*destroy", ""), mock(r"^aws ssm delete-parameter", "{}")]


def destructive(log):
    return [line for line in log if re.search(r"destroy|delete-objects|delete-parameter", line)]


@needs_ps
def test_destroy_needs_exact_project_name_and_dry_run_deletes_nothing(tmp_path):
    code, out, log, _ = run_ps(tmp_path, "destroy.ps1", "-DryRun", destroy_rules())
    assert code == 0 and "qglacierwatch-111122223333-ap-south-1" in out and not destructive(log)
    code, out, log, _ = run_ps(tmp_path, "destroy.ps1", "-ConfirmName wrong", destroy_rules())
    assert code == 2 and not destructive(log)
    code, out, log, _ = run_ps(tmp_path, "destroy.ps1", "-Orphans", destroy_rules())
    assert code == 0 and not destructive(log) and "Nothing was deleted" in out
    code, out, log, _ = run_ps(tmp_path, "destroy.ps1", "-ConfirmName qglacierwatch", destroy_rules())
    assert code == 0, out
    assert any("terraform" in line and "destroy" in line for line in log)
    assert sum("ssm delete-parameter" in line for line in log) == 2


@needs_ps
def test_deploy_refuses_missing_image_before_touching_terraform(tmp_path):
    rules = [mock(r"^aws sts get-caller-identity", IDENT), mock(r"^aws ecr describe-images .*imageTag=live", {"imageDetails": [{}]}),
             mock(r"^aws ecr describe-images", None, 254)]
    (tmp_path / "tf").mkdir()
    (tmp_path / "tf" / "terraform.tfvars").write_text('alert_email = "a@b.c"\ncreate_compute = false\n')
    code, out, log, tf = run_ps(tmp_path, "deploy.ps1", "-ImageTag abc1234 -Yes", rules)
    assert code != 0 and "not in ECR" in out
    assert not any(line.startswith("terraform") for line in log)
    assert "create_compute = false" in (tf / "terraform.tfvars").read_text()


@needs_ps
def test_status_prints_api_and_dashboard_urls(tmp_path):
    rules = [
        mock(r"^aws sts get-caller-identity", IDENT),
        mock(r"^aws lambda get-function-url-config", {"FunctionUrl": "https://abc.lambda-url.ap-south-1.on.aws/"}),
        mock(r"^aws ecs describe-services", {"services": [{"status": "ACTIVE", "desiredCount": 1, "runningCount": 1}]}),
        mock(r"^aws ecs list-tasks", {"taskArns": ["arn:task/1"]}),
        mock(r"^aws ecs describe-tasks", {"tasks": [{"lastStatus": "RUNNING", "attachments": [{"details": [{"name": "networkInterfaceId", "value": "eni-1"}]}]}]}),
        mock(r"^aws ec2 describe-network-interfaces", {"NetworkInterfaces": [{"Association": {"PublicIp": "203.0.113.7"}}]}),
    ]
    code, out, log, _ = run_ps(tmp_path, "status.ps1", "", rules)
    assert code == 0, out
    assert "API URL       : https://abc.lambda-url.ap-south-1.on.aws/" in out
    assert "http://203.0.113.7:8501" in out
    assert not any(re.search(r"create|put-|update-|delete", line) for line in log), "status must be read-only"


@needs_ps
def test_pause_writes_tfvars_and_applies_only_the_saved_plan(tmp_path):
    rules = [mock(r"^aws sts get-caller-identity", IDENT), mock(r"^terraform .* plan ", ""), mock(r"^terraform .* apply ", "")]
    (tmp_path / "tf").mkdir()
    (tmp_path / "tf" / "terraform.tfvars").write_text('alert_email = "a@b.c"\ncreate_compute = true\napi_image_tag = "abc1234"\n')
    code, out, log, tf = run_ps(tmp_path, "pause.ps1", "-Yes", rules)
    assert code == 0, out
    v = (tf / "terraform.tfvars").read_text()
    assert "dashboard_enabled = false" in v and "schedules_enabled = false" in v and 'api_image_tag = "abc1234"' in v
    tf_calls = [line for line in log if line.startswith("terraform")]
    assert " plan -input=false -out=tfplan" in tf_calls[0] and tf_calls[1].endswith("apply -input=false tfplan")
