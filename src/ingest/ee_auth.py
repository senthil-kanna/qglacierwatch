"""Earth Engine initialisation for local use (user credentials) and containers (service account).

In the cloud the service-account key JSON is kept in a secret store (AWS SSM Parameter Store, or
Azure Key Vault for the alternative deployment) and injected as EE_SERVICE_ACCOUNT_JSON. Locally,
`earthengine authenticate` credentials are used.
"""

import json
import os

import ee

from src import config


def initialize() -> None:
    key = os.getenv("EE_SERVICE_ACCOUNT_JSON", "").strip()
    if key and not key.startswith("{"):
        # The deploy tooling stores a placeholder until a real key is supplied (see docs/aws-deployment.md).
        raise RuntimeError(
            "EE_SERVICE_ACCOUNT_JSON is a placeholder, not a service-account key. Store the key with "
            "`aws ssm put-parameter --name /qgw/ee-service-account-json --type SecureString --overwrite "
            "--value file://ee-key.json` (AWS) or `az keyvault secret set ... --file ee-key.json` (Azure)."
        )
    if key:
        info = json.loads(key)
        creds = ee.ServiceAccountCredentials(info["client_email"], key_data=key)
        ee.Initialize(creds, project=config.EE_PROJECT)
    else:
        ee.Initialize(project=config.EE_PROJECT)
