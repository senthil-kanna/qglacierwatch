"""Earth Engine initialisation for local use (user credentials) and containers (service account).

In Azure the service-account key JSON is stored in Key Vault and injected as the secret env var
EE_SERVICE_ACCOUNT_JSON. Locally, `earthengine authenticate` credentials are used.
"""

import json
import os

import ee

from src import config


def initialize() -> None:
    key = os.getenv("EE_SERVICE_ACCOUNT_JSON", "").strip()
    if key and not key.startswith("{"):
        # scripts/azure/deploy.ps1 stores a placeholder until a real key is supplied, because a
        # Container Apps revision cannot start while a referenced Key Vault secret is missing.
        raise RuntimeError(
            "EE_SERVICE_ACCOUNT_JSON is a placeholder, not a service-account key. Store the key with "
            "`az keyvault secret set --vault-name <kv> -n ee-service-account-json --file ee-key.json`."
        )
    if key:
        info = json.loads(key)
        creds = ee.ServiceAccountCredentials(info["client_email"], key_data=key)
        ee.Initialize(creds, project=config.EE_PROJECT)
    else:
        ee.Initialize(project=config.EE_PROJECT)
