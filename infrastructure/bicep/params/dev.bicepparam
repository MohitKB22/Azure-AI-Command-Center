using '../main.bicep'

param environmentName = 'dev'
param namePrefix = 'aiccdev'
// Object ID of the Entra group that administers Key Vault in this environment.
param keyVaultAdminObjectId = readEnvironmentVariable('KEYVAULT_ADMIN_OBJECT_ID', '')
