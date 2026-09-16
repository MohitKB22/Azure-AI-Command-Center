using '../main.bicep'

param environmentName = 'staging'
param namePrefix = 'aiccstg'
param keyVaultAdminObjectId = readEnvironmentVariable('KEYVAULT_ADMIN_OBJECT_ID', '')
