// QGlacierWatch on Azure, sized for an Azure for Students subscription ($100 credit).
// Everything scales to zero or is pay-per-use; see docs/deployment.md for the cost model.
//
//   az group create -n rg-qglacierwatch -l centralindia
//   az deployment group create -g rg-qglacierwatch -f infra/main.bicep -p infra/main.parameters.json
//
// Resources: Log Analytics (daily cap), ACR Basic, Storage (Azure Files share for data/artifacts/reports),
// Key Vault (RBAC), user-assigned identity, Container Apps environment (Consumption), API and
// dashboard apps (min replicas 0), scheduled jobs, and a monthly budget with e-mail alerts.

targetScope = 'resourceGroup'

@description('Short prefix for resource names (lowercase letters/digits).')
@maxLength(10)
param prefix string = 'qgw'

@description('Region. Student subscriptions allow only some regions; check `az account list-locations` and the subscription policy.')
param location string = resourceGroup().location

@description('Container image tag pushed by the CD workflow, e.g. a git SHA. Leave the default for the first deployment before any image exists.')
param imageTag string = 'bootstrap'

@description('Deploy the container apps and jobs. Set false for the first run, push an image, then redeploy with true.')
param deployApps bool = false

@description('true: private Azure Container Registry Basic (~USD 5/month). false: pull a PUBLIC image from externalImage (e.g. GitHub Container Registry, free) and skip ACR.')
param useAcr bool = true

@description('Public image repository used when useAcr = false, without tag.')
param externalImage string = 'ghcr.io/senthil-kanna/qglacierwatch'

@description('Monthly budget in USD for the resource group.')
param monthlyBudgetUsd int = 20

@description('E-mail for budget alerts.')
param alertEmail string

@description('Budget start date (first day of a month, yyyy-MM-01).')
param budgetStartDate string

@description('Earth Engine project id used by ingestion jobs.')
param eeProject string = 'ee-senthil-hydro'

var suffix = uniqueString(resourceGroup().id)
var acrName = toLower('${prefix}acr${suffix}')
var storageName = toLower(take('${prefix}st${suffix}', 24))
var kvName = toLower(take('${prefix}-kv-${suffix}', 24))
var shareName = 'qgw'
var image = useAcr ? '${acr!.properties.loginServer}/qglacierwatch:${imageTag}' : '${externalImage}:${imageTag}'
var commonEnv = [
  { name: 'QGW_MODE', value: 'real' }
  { name: 'QGW_DATA', value: '/mnt/qgw/data' }
  { name: 'QGW_ARTIFACTS', value: '/mnt/qgw/artifacts' }
  { name: 'QGW_REPORTS', value: '/mnt/qgw/reports' }
  { name: 'EE_PROJECT', value: eeProject }
  { name: 'MLFLOW_DISABLE_AGENT_HINT', value: '1' }
]
var volumeMounts = [ { volumeName: 'qgw', mountPath: '/mnt/qgw' } ]
var volumes = [ { name: 'qgw', storageType: 'AzureFile', storageName: 'qgwfiles' } ]

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${prefix}-logs-${suffix}'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
    workspaceCapping: { dailyQuotaGb: json('0.2') } // hard cap on ingestion cost
  }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = if (useAcr) {
  name: acrName
  location: location
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource share 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: fileService
  name: shareName
  properties: { shareQuota: 10 } // GiB
}

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: kvName
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${prefix}-id-${suffix}'
  location: location
}

// AcrPull and Key Vault Secrets User for the apps' identity (no registry passwords anywhere).
resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (useAcr) {
  scope: acr
  name: guid(resourceGroup().id, identity.id, 'acrpull')
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource kvSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: kv
  name: guid(kv.id, identity.id, 'kvsecretsuser')
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${prefix}-env-${suffix}'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
    workloadProfiles: [ { name: 'Consumption', workloadProfileType: 'Consumption' } ]
  }
}

resource envStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: env
  name: 'qgwfiles'
  properties: {
    azureFile: {
      accountName: storage.name
      accountKey: storage.listKeys().keys[0].value
      shareName: shareName
      accessMode: 'ReadWrite'
    }
  }
}

var registries = useAcr ? [ { server: acr!.properties.loginServer, identity: identity.id } ] : []
// Secrets are references to Key Vault; values are set out of band (`az keyvault secret set`).
var kvSecrets = [
  { name: 'qgw-api-key', keyVaultUrl: '${kv.properties.vaultUri}secrets/qgw-api-key', identity: identity.id }
  { name: 'ee-service-account-json', keyVaultUrl: '${kv.properties.vaultUri}secrets/ee-service-account-json', identity: identity.id }
]

resource api 'Microsoft.App/containerApps@2024-03-01' = if (deployApps) {
  name: '${prefix}-api'
  location: location
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identity.id}': {} } }
  dependsOn: [ acrPull, kvSecretsUser, envStorage ]
  properties: {
    environmentId: env.id
    workloadProfileName: 'Consumption'
    configuration: {
      ingress: { external: true, targetPort: 8000, transport: 'auto', allowInsecure: false }
      registries: registries
      secrets: [ kvSecrets[0] ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: image
          args: [ 'api' ]
          env: concat(commonEnv, [ { name: 'QGW_API_KEY', secretRef: 'qgw-api-key' } ])
          resources: { cpu: json('0.5'), memory: '1Gi' }
          volumeMounts: volumeMounts
          probes: [
            { type: 'Liveness', httpGet: { path: '/health', port: 8000 }, periodSeconds: 30, initialDelaySeconds: 20 }
            { type: 'Readiness', httpGet: { path: '/health', port: 8000 }, periodSeconds: 15, initialDelaySeconds: 10 }
          ]
        }
      ]
      scale: { minReplicas: 0, maxReplicas: 2, rules: [ { name: 'http', http: { metadata: { concurrentRequests: '30' } } } ] }
      volumes: volumes
    }
  }
}

resource dashboard 'Microsoft.App/containerApps@2024-03-01' = if (deployApps) {
  name: '${prefix}-dashboard'
  location: location
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identity.id}': {} } }
  dependsOn: [ acrPull, envStorage ]
  properties: {
    environmentId: env.id
    workloadProfileName: 'Consumption'
    configuration: {
      ingress: { external: true, targetPort: 8501, transport: 'auto', allowInsecure: false, stickySessions: { affinity: 'sticky' } }
      registries: registries
    }
    template: {
      containers: [
        {
          name: 'dashboard'
          image: image
          args: [ 'dashboard' ]
          env: commonEnv
          resources: { cpu: json('0.5'), memory: '1Gi' }
          volumeMounts: volumeMounts
          probes: [ { type: 'Liveness', httpGet: { path: '/_stcore/health', port: 8501 }, periodSeconds: 30, initialDelaySeconds: 30 } ]
        }
      ]
      scale: { minReplicas: 0, maxReplicas: 1 }
      volumes: volumes
    }
  }
}

// Scheduled and manual jobs. Each runs one pipeline module and exits (billed per second).
var jobs = [
  { name: 'ingest', cron: '0 2 * * 1', args: [ 'job', 'src.pipeline.refresh' ], cpu: '1.0', mem: '2Gi', manual: false }
  { name: 'drift', cron: '0 4 * * 1', args: [ 'job', 'src.drift.replay', '--latest' ], cpu: '0.5', mem: '1Gi', manual: false }
  { name: 'train', cron: '', args: [ 'job', 'src.pipeline.train', '--final' ], cpu: '2.0', mem: '4Gi', manual: true }
  { name: 'lakes', cron: '', args: [ 'job', 'src.lakes.pipeline' ], cpu: '0.5', mem: '1Gi', manual: true }
]

resource jobRes 'Microsoft.App/jobs@2024-03-01' = [for j in jobs: if (deployApps) {
  name: '${prefix}-job-${j.name}'
  location: location
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identity.id}': {} } }
  dependsOn: [ acrPull, kvSecretsUser, envStorage ]
  properties: {
    environmentId: env.id
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: j.manual ? 'Manual' : 'Schedule'
      scheduleTriggerConfig: j.manual ? null : { cronExpression: j.cron, parallelism: 1, replicaCompletionCount: 1 }
      manualTriggerConfig: j.manual ? { parallelism: 1, replicaCompletionCount: 1 } : null
      replicaTimeout: 3600
      replicaRetryLimit: 1
      registries: registries
      secrets: [ kvSecrets[1] ]
    }
    template: {
      containers: [
        {
          name: j.name
          image: image
          args: j.args
          env: concat(commonEnv, [ { name: 'EE_SERVICE_ACCOUNT_JSON', secretRef: 'ee-service-account-json' } ])
          resources: { cpu: json(j.cpu), memory: j.mem }
          volumeMounts: volumeMounts
        }
      ]
      volumes: volumes
    }
  }
}]

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: '${prefix}-monthly-budget'
  properties: {
    category: 'Cost'
    amount: monthlyBudgetUsd
    timeGrain: 'Monthly'
    timePeriod: { startDate: budgetStartDate }
    notifications: {
      actual50: { enabled: true, operator: 'GreaterThan', threshold: 50, contactEmails: [ alertEmail ], thresholdType: 'Actual' }
      actual80: { enabled: true, operator: 'GreaterThan', threshold: 80, contactEmails: [ alertEmail ], thresholdType: 'Actual' }
      forecast100: { enabled: true, operator: 'GreaterThan', threshold: 100, contactEmails: [ alertEmail ], thresholdType: 'Forecasted' }
    }
  }
}

output acrLoginServer string = useAcr ? acr!.properties.loginServer : ''
output acrName string = useAcr ? acr!.name : ''
output keyVaultName string = kv.name
output storageAccount string = storage.name
output fileShare string = shareName
output identityClientId string = identity.properties.clientId
output apiUrl string = deployApps ? 'https://${api!.properties.configuration.ingress.fqdn}' : ''
output dashboardUrl string = deployApps ? 'https://${dashboard!.properties.configuration.ingress.fqdn}' : ''
