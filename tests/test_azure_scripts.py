"""Azure deployment assets: template consistency, script syntax, and the safety logic of the
cleanup and pre-flight scripts, run against a fake `az` (tests/fixtures/az_mock.ps1). Nothing here
contacts Azure."""

import json
import os
import re
import shutil
import subprocess

import pytest

from src import config

ROOT = config.ROOT
SCRIPTS = ROOT / "scripts" / "azure"
MOCK = ROOT / "tests" / "fixtures" / "az_mock.ps1"
SHELL = shutil.which("pwsh") or shutil.which("powershell")
needs_ps = pytest.mark.skipif(SHELL is None, reason="PowerShell not available")

SUB = {"name": "Azure for Students", "id": "sub-1", "tenantId": "t-1", "state": "Enabled", "user": {"name": "me@x"}}


def run_script(tmp_path, script, args, rules):
    rules_file, log = tmp_path / "rules.json", tmp_path / "az.log"
    rules_file.write_text(json.dumps(rules))
    log.write_text("")
    cmd = f". '{MOCK}'; & '{SCRIPTS / script}' {args}; exit $LASTEXITCODE"
    env = {**os.environ, "AZ_MOCK_RULES": str(rules_file), "AZ_MOCK_LOG": str(log)}
    p = subprocess.run([SHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                       capture_output=True, text=True, env=env, timeout=120)
    return p.returncode, p.stdout + p.stderr, log.read_text().splitlines()


def rule(match, out=None, code=0):
    return {"match": match, "out": None if out is None else json.dumps(out) if not isinstance(out, str) else out, "exit": code}


TAG = {"project": "qglacierwatch"}
OURS = [{"name": "qgw-api", "type": "Microsoft.App/containerApps", "tags": TAG},
        {"name": "qgw-kv-abc", "type": "Microsoft.KeyVault/vaults", "tags": TAG}]


def cleanup_rules(rg_tags=TAG, resources=OURS):
    return [rule(r"^account show", SUB), rule(r"^group show", {"name": "rg-qglacierwatch", "location": "centralindia", "tags": rg_tags}),
            rule(r"^resource list", resources), rule(r"^group delete", ""), rule(r"^group exists", "false")]


def deleted(log):
    return any(line.startswith("group delete") for line in log)


# --- template and configuration consistency -----------------------------------------------------

def test_mount_uid_matches_container_user():
    bicep = (ROOT / "infra" / "main.bicep").read_text()
    docker = (ROOT / "docker" / "Dockerfile").read_text()
    uid = re.search(r"uid=(\d+),gid=(\d+)", bicep)
    assert uid, "Azure Files mountOptions must set uid/gid for the non-root user"
    assert f"--uid {uid.group(1)}" in docker and f"--gid {uid.group(2)}" in docker


def test_parameters_use_public_ghcr_and_contain_no_secrets():
    p = json.loads((ROOT / "infra" / "main.parameters.json").read_text())["parameters"]
    assert p["useAcr"]["value"] is False and p["externalImage"]["value"].startswith("ghcr.io/")
    env = (ROOT / ".env.example").read_text()
    for line in env.splitlines():
        m = re.match(r"\s*([A-Z_]*(KEY|SECRET|PASSWORD|TOKEN)[A-Z_]*)=(\S*)", line)
        if m:
            assert m.group(3) == "" or m.group(3).startswith("#"), f"{m.group(1)} must be empty in .env.example"


def test_every_tagged_resource_type_in_template():
    bicep = (ROOT / "infra" / "main.bicep").read_text()
    # Each top-level resource with a location also carries the project tags (cleanup relies on it).
    assert bicep.count("tags: tags") >= bicep.count("location: location") + bicep.count("location: 'global'")


@pytest.mark.skipif(shutil.which("az") is None, reason="Azure CLI not installed")
def test_bicep_compiles():
    p = subprocess.run([shutil.which("az"), "bicep", "build", "--file", str(ROOT / "infra" / "main.bicep"), "--stdout"], capture_output=True, text=True)
    if "Bicep CLI not found" in p.stderr or "bicep" in p.stderr.lower() and "install" in p.stderr.lower():
        pytest.skip("Bicep CLI not installed")
    assert p.returncode == 0, p.stderr


def test_ee_placeholder_secret_fails_with_clear_message(monkeypatch):
    from src.ingest import ee_auth

    monkeypatch.setenv("EE_SERVICE_ACCOUNT_JSON", "not-configured")
    with pytest.raises(RuntimeError, match="placeholder"):
        ee_auth.initialize()


# --- script syntax --------------------------------------------------------------------------------

@needs_ps
@pytest.mark.parametrize("script", ["common.ps1", "preflight.ps1", "deploy.ps1", "verify.ps1", "cleanup.ps1"])
def test_scripts_parse(script):
    cmd = (f"$e=$null; [System.Management.Automation.Language.Parser]::ParseFile('{SCRIPTS / script}', [ref]$null, [ref]$e) | Out-Null; "
           "if ($e.Count) { $e | % { $_.ToString() }; exit 1 }")
    p = subprocess.run([SHELL, "-NoProfile", "-NonInteractive", "-Command", cmd], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr


# --- cleanup safety -----------------------------------------------------------------------------------

@needs_ps
def test_cleanup_deletes_only_after_exact_confirmation(tmp_path):
    code, out, log = run_script(tmp_path, "cleanup.ps1", "-ConfirmName wrong-name", cleanup_rules())
    assert code == 2 and not deleted(log)
    assert "Azure for Students (sub-1)" in out and "rg-qglacierwatch" in out
    code, out, log = run_script(tmp_path, "cleanup.ps1", "-ConfirmName rg-qglacierwatch", cleanup_rules())
    assert code == 0 and deleted(log)


@needs_ps
def test_cleanup_refuses_untagged_group_or_foreign_resources(tmp_path):
    code, _, log = run_script(tmp_path, "cleanup.ps1", "-ConfirmName rg-qglacierwatch", cleanup_rules(rg_tags={}))
    assert code == 1 and not deleted(log)
    foreign = OURS + [{"name": "someone-elses-db", "type": "Microsoft.Sql/servers", "tags": None}]
    code, out, log = run_script(tmp_path, "cleanup.ps1", "-ConfirmName rg-qglacierwatch", cleanup_rules(resources=foreign))
    assert code == 1 and not deleted(log) and "someone-elses-db" in out


@needs_ps
def test_cleanup_dry_run_and_subscription_mismatch_never_delete(tmp_path):
    code, _, log = run_script(tmp_path, "cleanup.ps1", "-DryRun", cleanup_rules())
    assert code == 0 and not deleted(log)
    code, _, log = run_script(tmp_path, "cleanup.ps1", "-SubscriptionId other-sub -ConfirmName rg-qglacierwatch", cleanup_rules())
    assert code == 1 and not deleted(log)


# --- pre-flight checks ----------------------------------------------------------------------------

def preflight_rules(state="Enabled", allowed=("centralindia",), registered=True):
    perms = {"value": [{"actions": ["*"], "notActions": []}]}
    return [
        rule(r"^account show", {**SUB, "state": state}),
        rule(r"^rest .*subscriptions/sub-1\?api", {"subscriptionPolicies": {"quotaId": "AzureForStudents_2018-01-01", "spendingLimit": "On"}}),
        rule(r"^account list-locations", {"name": "centralindia", "displayName": "Central India"}),
        rule(r"^policy assignment list", [{"parameters": {"listOfAllowedLocations": {"value": list(allowed)}}}]),
        rule(r"^provider show -n Microsoft.App --query resourceTypes", ["Central India"]),
        rule(r"^provider show", {"s": "Registered" if registered else "NotRegistered"}),
        rule(r"^rest .*Microsoft.App/locations", {"value": [{"name": {"value": "ManagedEnvironmentCount"}, "currentValue": 0, "limit": 15}]}),
        rule(r"^storage account show-usage", {"currentValue": 0, "limit": 250}),
        rule(r"^rest .*permissions", perms),
        rule(r"^ad signed-in-user", "00000000-0000-0000-0000-000000000001"),
        rule(r"^bicep build", ""),
        rule(r"^group show", None, 3),
    ]


@needs_ps
def test_preflight_passes_on_a_healthy_student_subscription(tmp_path):
    code, out, log = run_script(tmp_path, "preflight.ps1", "", preflight_rules())
    assert code == 0, out
    assert "Nothing was created" in out
    assert not any(re.match(r"^(group create|deployment|provider register)", line) for line in log)


@needs_ps
@pytest.mark.parametrize("kw,expect", [
    ({"state": "Disabled"}, "Subscription state is 'Disabled'"),
    ({"allowed": ("eastus", "westeurope")}, "Policy does not allow centralindia"),
    ({"registered": False}, "-RegisterProviders"),
])
def test_preflight_fails_clearly(tmp_path, kw, expect):
    code, out, _ = run_script(tmp_path, "preflight.ps1", "", preflight_rules(**kw))
    assert code == 1 and expect in out, out
