// Azure AI Command Center — core infrastructure.
//
// Design notes:
//   * No secret is ever passed as a template parameter in plaintext. Application
//     credentials live in Key Vault and are read through Managed Identity.
//   * The API's user-assigned identity is granted the narrowest role that works
//     for each resource, rather than Contributor on the resource group.
//   * PostgreSQL and Storage disable public access paths that are not required.

targetScope = 'resourceGroup'

@description('Deployment environment. Drives sizing and public access rules.')
@allowed(['dev', 'staging', 'production'])
param environmentName string

@description('Azure region for every resource.')
param location string = resourceGroup().location

@description('Short prefix used to name resources. Lowercase letters and digits only.')
@minLength(3)
@maxLength(11)
param namePrefix string

@description('Administrator login for PostgreSQL. The password is generated and stored in Key Vault.')
param postgresAdminUser string = 'aiccadmin'

@description('Object ID of the group that should administer Key Vault.')
param keyVaultAdminObjectId string

@description('Azure OpenAI model deployments to create.')
param openAiDeployments array = [
  { name: 'gpt-4o', model: 'gpt-4o', version: '2024-08-06', capacity: 10 }
  { name: 'text-embedding-3-large', model: 'text-embedding-3-large', version: '1', capacity: 30 }
]

var suffix = uniqueString(resourceGroup().id)
var isProduction = environmentName == 'production'
var tags = {
  application: 'azure-ai-command-center'
  environment: environmentName
  managedBy: 'bicep'
}

// ---------------------------------------------------------------- identity

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-id-${suffix}'
  location: location
  tags: tags
}

// ------------------------------------------------------------ observability

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${namePrefix}-log-${suffix}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: isProduction ? 90 : 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${namePrefix}-appi-${suffix}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    IngestionMode: 'LogAnalytics'
  }
}

// ------------------------------------------------------------------ secrets

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: '${namePrefix}-kv-${suffix}'
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: isProduction ? 90 : 7
    enablePurgeProtection: isProduction ? true : null
    publicNetworkAccess: isProduction ? 'Disabled' : 'Enabled'
    networkAcls: { defaultAction: isProduction ? 'Deny' : 'Allow', bypass: 'AzureServices' }
  }
}

// ------------------------------------------------------------------ storage

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: toLower('${namePrefix}st${take(suffix, 8)}')
  location: location
  tags: tags
  sku: { name: isProduction ? 'Standard_ZRS' : 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false // force Entra ID auth; no account keys anywhere
    publicNetworkAccess: isProduction ? 'Disabled' : 'Enabled'
    encryption: {
      services: { blob: { enabled: true }, file: { enabled: true } }
      keySource: 'Microsoft.Storage'
    }
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    deleteRetentionPolicy: { enabled: true, days: isProduction ? 30 : 7 }
  }
}

resource documentsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'documents'
  properties: { publicAccess: 'None' }
}

// ------------------------------------------------------------------- openai

resource openAi 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: '${namePrefix}-aoai-${suffix}'
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: '${namePrefix}-aoai-${suffix}'
    publicNetworkAccess: isProduction ? 'Disabled' : 'Enabled'
    disableLocalAuth: true // Managed Identity only — no API keys issued
  }
}

@batchSize(1) // Azure OpenAI rejects parallel deployment creation on one account
resource openAiDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = [
  for deployment in openAiDeployments: {
    parent: openAi
    name: deployment.name
    sku: { name: 'Standard', capacity: deployment.capacity }
    properties: {
      model: { format: 'OpenAI', name: deployment.model, version: deployment.version }
      versionUpgradeOption: 'OnceCurrentVersionExpired'
    }
  }
]

// ------------------------------------------------------------------- search

resource search 'Microsoft.Search/searchServices@2024-06-01-preview' = {
  name: '${namePrefix}-srch-${suffix}'
  location: location
  tags: tags
  sku: { name: isProduction ? 'standard' : 'basic' }
  identity: { type: 'SystemAssigned' }
  properties: {
    replicaCount: isProduction ? 2 : 1
    partitionCount: 1
    authOptions: null
    disableLocalAuth: true
    publicNetworkAccess: isProduction ? 'disabled' : 'enabled'
  }
}

// --------------------------------------------------------------- postgresql

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: '${namePrefix}-pg-${suffix}'
  location: location
  tags: tags
  sku: {
    name: isProduction ? 'Standard_D2ds_v5' : 'Standard_B1ms'
    tier: isProduction ? 'GeneralPurpose' : 'Burstable'
  }
  properties: {
    version: '16'
    administratorLogin: postgresAdminUser
    // Entra-only authentication: no password is created or stored anywhere.
    authConfig: { activeDirectoryAuth: 'Enabled', passwordAuth: 'Disabled', tenantId: subscription().tenantId }
    storage: { storageSizeGB: isProduction ? 128 : 32, autoGrow: 'Enabled' }
    backup: {
      backupRetentionDays: isProduction ? 35 : 7
      geoRedundantBackup: isProduction ? 'Enabled' : 'Disabled'
    }
    highAvailability: { mode: isProduction ? 'ZoneRedundant' : 'Disabled' }
    network: { publicNetworkAccess: isProduction ? 'Disabled' : 'Enabled' }
  }
}

resource postgresDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: 'aicc'
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}

// ---------------------------------------------------------- container apps

resource containerEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${namePrefix}-cae-${suffix}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    zoneRedundant: isProduction
  }
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: toLower('${namePrefix}acr${take(suffix, 8)}')
  location: location
  tags: tags
  sku: { name: isProduction ? 'Premium' : 'Basic' }
  properties: {
    adminUserEnabled: false // pulls use the managed identity below
  }
}

// -------------------------------------------------- role assignments (RBAC)

var roles = {
  keyVaultSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
  keyVaultAdministrator: '00482a5a-887f-4fb3-b363-3b7fe8e74483'
  storageBlobDataContributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  cognitiveServicesOpenAiUser: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
  searchIndexDataContributor: '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
  acrPull: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
  monitoringReader: '43d0d8ad-25c7-4714-9337-8ba259a9fe05'
}

resource kvSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: keyVault
  name: guid(keyVault.id, identity.id, roles.keyVaultSecretsUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.keyVaultSecretsUser)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource kvAdmin 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: keyVault
  name: guid(keyVault.id, keyVaultAdminObjectId, roles.keyVaultAdministrator)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.keyVaultAdministrator)
    principalId: keyVaultAdminObjectId
  }
}

resource blobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, identity.id, roles.storageBlobDataContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataContributor)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource openAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: openAi
  name: guid(openAi.id, identity.id, roles.cognitiveServicesOpenAiUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesOpenAiUser)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource searchContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: search
  name: guid(search.id, identity.id, roles.searchIndexDataContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.searchIndexDataContributor)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: registry
  name: guid(registry.id, identity.id, roles.acrPull)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPull)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ------------------------------------------------------------------ outputs

output identityClientId string = identity.properties.clientId
output identityPrincipalId string = identity.properties.principalId
output keyVaultUri string = keyVault.properties.vaultUri
output storageAccountUrl string = storage.properties.primaryEndpoints.blob
output openAiEndpoint string = openAi.properties.endpoint
output searchEndpoint string = 'https://${search.name}.search.windows.net'
output postgresFqdn string = postgres.properties.fullyQualifiedDomainName
output postgresDatabaseName string = postgresDatabase.name
output containerEnvironmentId string = containerEnvironment.id
output registryLoginServer string = registry.properties.loginServer
output appInsightsConnectionString string = appInsights.properties.ConnectionString
output logAnalyticsWorkspaceId string = logAnalytics.id
