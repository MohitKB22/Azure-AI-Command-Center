using '../main.bicep'

param environmentName = 'production'
param namePrefix = 'aiccprd'
param keyVaultAdminObjectId = readEnvironmentVariable('KEYVAULT_ADMIN_OBJECT_ID', '')
param openAiDeployments = [
  { name: 'gpt-4o', model: 'gpt-4o', version: '2024-08-06', capacity: 60 }
  { name: 'gpt-4o-mini', model: 'gpt-4o-mini', version: '2024-07-18', capacity: 120 }
  { name: 'text-embedding-3-large', model: 'text-embedding-3-large', version: '1', capacity: 120 }
]
