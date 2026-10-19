"""Earth Engine initialisation for local use (user credentials) and containers (service account).

In Azure the service-account key JSON is stored in Key Vault and injected as the secret env var
EE_SERVICE_ACCOUNT_JSON. Locally, `earthengine authenticate` credentials are used.
"""

import json
import os

import ee

from src import config


def initialize() -> None:
    key = os.getenv("EE_SERVICE_ACCOUNT_JSON")
    if key:
        info = json.loads(key)
        creds = ee.ServiceAccountCredentials(info["client_email"], key_data=key)
        ee.Initialize(creds, project=config.EE_PROJECT)
    else:
        ee.Initialize(project=config.EE_PROJECT)
