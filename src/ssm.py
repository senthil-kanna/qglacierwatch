"""Secrets from AWS SSM Parameter Store (SecureString), read at runtime so they never sit in
Terraform state, Lambda/ECS environment variables or the image. Parameters are created with the
placeholder value below by scripts/aws/bootstrap.ps1; the real value is set with
`aws ssm put-parameter --overwrite`."""

import os

PLACEHOLDER = "not-configured"


def get(name: str | None) -> str | None:
    """Decrypted value of parameter `name`, or None when unset, empty or still the placeholder."""
    if not name:
        return None
    import boto3

    value = boto3.client("ssm").get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"].strip()
    return None if not value or value == PLACEHOLDER else value


def load_env(var: str, param_env: str) -> bool:
    """Set os.environ[var] from the parameter named by os.environ[param_env] unless var is already set."""
    if os.getenv(var):
        return False
    value = get(os.getenv(param_env))
    if value is None:
        return False
    os.environ[var] = value
    return True
