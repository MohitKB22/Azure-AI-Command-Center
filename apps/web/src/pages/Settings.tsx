import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  Badge,
  ConfirmDialog,
  DataTable,
  ErrorState,
  Field,
  LoadingPanel,
  Modal,
  PageHeader,
  Panel,
  useToast,
} from '@/components/ui'
import { api } from '@/lib/api'
import { formatDateTime, titleCase } from '@/lib/format'
import type { Page, SystemHealth, User } from '@/lib/types'
import { useAuthStore } from '@/store/auth'

interface ApiKey {
  id: string
  name: string
  key_prefix: string
  created_at: string
  expires_at: string | null
  revoked_at: string | null
  last_used_at: string | null
}

interface RoleInfo {
  value: string
  label: string
  permissions: string[]
}

export function SettingsPage() {
  const queryClient = useQueryClient()
  const { notify } = useToast()
  const { user, permissions, can } = useAuthStore()

  const [keyName, setKeyName] = useState('')
  const [issuedKey, setIssuedKey] = useState<string | null>(null)
  const [revoking, setRevoking] = useState<ApiKey | null>(null)

  const health = useQuery({ queryKey: ['system-health'], queryFn: () => api.get<SystemHealth>('/monitoring/health') })
  const keys = useQuery({ queryKey: ['api-keys'], queryFn: () => api.get<ApiKey[]>('/auth/api-keys') })
  const users = useQuery({
    queryKey: ['users'],
    queryFn: () => api.get<Page<User>>('/users?page_size=50'),
    enabled: can('users:read'),
  })
  const roles = useQuery({
    queryKey: ['roles'],
    queryFn: () => api.get<RoleInfo[]>('/users/roles'),
    enabled: can('users:read'),
  })

  const createKey = useMutation({
    mutationFn: () => api.post<{ api_key: ApiKey; key: string }>('/auth/api-keys', { name: keyName }),
    onSuccess: (response) => {
      setIssuedKey(response.key)
      setKeyName('')
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
    },
    onError: (error: Error) => notify(error.message, 'danger'),
  })

  const revoke = useMutation({
    mutationFn: (id: string) => api.delete(`/auth/api-keys/${id}`),
    onSuccess: () => {
      notify('API key revoked.', 'info')
      setRevoking(null)
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
    },
  })

  return (
    <>
      <PageHeader title="Settings" description="Runtime configuration, access keys, roles and platform users." />

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Runtime configuration" description="Read-only — everything here comes from environment variables">
          {health.isLoading ? (
            <LoadingPanel rows={5} />
          ) : health.error ? (
            <ErrorState error={health.error} onRetry={() => health.refetch()} />
          ) : (
            <>
              <dl className="space-y-2 text-sm">
                {[
                  ['Environment', health.data?.environment],
                  ['Demo mode', health.data?.demo_mode ? 'enabled' : 'disabled'],
                  ['LLM provider', health.data?.providers.llm],
                  ['Embedding provider', health.data?.providers.embeddings],
                  ['Vector store', health.data?.providers.vector_store],
                  ['Blob storage', health.data?.providers.blob],
                  ['Python', health.data?.python],
                ].map(([label, value]) => (
                  <div key={String(label)} className="flex justify-between gap-3 border-b border-border/50 pb-1">
                    <dt className="text-xs text-slate-400">{label}</dt>
                    <dd className="font-mono text-xs text-slate-200">{String(value)}</dd>
                  </div>
                ))}
              </dl>
              {(health.data?.configuration_warnings.length ?? 0) > 0 && (
                <ul className="mt-3 space-y-1 rounded border border-warn/40 bg-warn/10 px-3 py-2 text-xs text-amber-200">
                  {health.data?.configuration_warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              )}
              <p className="mt-3 text-[11px] text-slate-500">
                Secrets are never returned by the API. To switch providers, set the relevant environment variables and
                restart the service.
              </p>
            </>
          )}
        </Panel>

        <Panel title="Your session">
          <dl className="space-y-2 text-sm">
            {[
              ['Name', user?.full_name],
              ['Email', user?.email],
              ['Role', user ? titleCase(user.role) : '—'],
              ['Team', user?.team ?? '—'],
              ['Last sign-in', formatDateTime(user?.last_login_at)],
            ].map(([label, value]) => (
              <div key={String(label)} className="flex justify-between gap-3 border-b border-border/50 pb-1">
                <dt className="text-xs text-slate-400">{label}</dt>
                <dd className="text-xs text-slate-200">{String(value)}</dd>
              </div>
            ))}
          </dl>
          <div className="mt-3">
            <p className="mb-1 text-xs text-slate-400">Your permissions ({permissions.length})</p>
            <div className="flex max-h-32 flex-wrap gap-1 overflow-y-auto">
              {permissions.map((permission) => (
                <Badge key={permission} tone="neutral">
                  {permission}
                </Badge>
              ))}
            </div>
          </div>
        </Panel>
      </div>

      <Panel
        className="mt-4"
        title="API keys"
        description="For CI/CD and enterprise integrations. Sent as the X-API-Key header."
      >
        {can('settings:write') && (
          <div className="mb-3 flex flex-wrap items-end gap-2">
            <Field label="Key name">
              <input
                className="field w-64"
                value={keyName}
                placeholder="github-actions"
                onChange={(event) => setKeyName(event.target.value)}
              />
            </Field>
            <button
              type="button"
              className="btn-primary"
              disabled={!keyName.trim() || createKey.isPending}
              onClick={() => createKey.mutate()}
            >
              {createKey.isPending ? 'Issuing…' : 'Issue key'}
            </button>
          </div>
        )}

        {keys.isLoading ? (
          <LoadingPanel rows={3} />
        ) : (
          <DataTable
            rows={keys.data ?? []}
            keyOf={(key) => key.id}
            emptyMessage="No API keys issued."
            columns={[
              { key: 'name', header: 'Name', render: (key) => key.name },
              {
                key: 'prefix',
                header: 'Prefix',
                render: (key) => <span className="font-mono text-xs">{key.key_prefix}…</span>,
              },
              {
                key: 'status',
                header: 'Status',
                render: (key) => (
                  <Badge tone={key.revoked_at ? 'danger' : 'success'}>{key.revoked_at ? 'revoked' : 'active'}</Badge>
                ),
              },
              { key: 'created', header: 'Created', render: (key) => formatDateTime(key.created_at) },
              { key: 'used', header: 'Last used', render: (key) => formatDateTime(key.last_used_at) },
              {
                key: 'actions',
                header: '',
                className: 'text-right',
                render: (key) =>
                  key.revoked_at ? null : (
                    <button type="button" className="btn-ghost px-2 py-1 text-[11px]" onClick={() => setRevoking(key)}>
                      Revoke
                    </button>
                  ),
              },
            ]}
          />
        )}
      </Panel>

      {can('users:read') && (
        <>
          <Panel className="mt-4" title="Users">
            {users.isLoading ? (
              <LoadingPanel rows={4} />
            ) : (
              <DataTable
                rows={users.data?.items ?? []}
                keyOf={(item) => item.id}
                emptyMessage="No users."
                columns={[
                  {
                    key: 'name',
                    header: 'User',
                    render: (item) => (
                      <div>
                        <p className="font-medium text-slate-100">{item.full_name}</p>
                        <p className="text-xs text-slate-500">{item.email}</p>
                      </div>
                    ),
                  },
                  { key: 'role', header: 'Role', render: (item) => <Badge tone="info">{titleCase(item.role)}</Badge> },
                  { key: 'team', header: 'Team', render: (item) => item.team ?? '—' },
                  {
                    key: 'status',
                    header: 'Status',
                    render: (item) => (
                      <Badge tone={item.is_active ? 'success' : 'neutral'}>{item.is_active ? 'active' : 'inactive'}</Badge>
                    ),
                  },
                  { key: 'last', header: 'Last sign-in', render: (item) => formatDateTime(item.last_login_at) },
                ]}
              />
            )}
          </Panel>

          <Panel className="mt-4" title="Roles and permissions">
            {roles.isLoading ? (
              <LoadingPanel rows={4} />
            ) : (
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {roles.data?.map((role) => (
                  <div key={role.value} className="rounded-md border border-border bg-canvas px-3 py-2">
                    <p className="text-sm font-medium text-slate-100">{role.label}</p>
                    <p className="mt-0.5 text-[11px] text-slate-500">{role.permissions.length} permissions</p>
                    <div className="mt-2 flex max-h-28 flex-wrap gap-1 overflow-y-auto">
                      {role.permissions.map((permission) => (
                        <Badge key={permission} tone="neutral">
                          {permission}
                        </Badge>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </>
      )}

      <Modal open={Boolean(issuedKey)} title="API key issued" onClose={() => setIssuedKey(null)}>
        <p className="text-sm text-slate-300">
          Copy this key now. It is hashed before storage and cannot be shown again.
        </p>
        <pre className="mt-3 break-all rounded border border-azure-500/30 bg-canvas p-3 font-mono text-xs text-azure-100">
          {issuedKey}
        </pre>
        <button
          type="button"
          className="btn-ghost mt-3"
          onClick={() => {
            if (issuedKey) navigator.clipboard?.writeText(issuedKey)
            notify('Copied to clipboard.', 'success')
          }}
        >
          Copy
        </button>
      </Modal>

      <ConfirmDialog
        open={Boolean(revoking)}
        title="Revoke API key"
        message={`"${revoking?.name}" will stop working immediately. Any integration using it will start receiving 401 responses.`}
        confirmLabel="Revoke"
        busy={revoke.isPending}
        onCancel={() => setRevoking(null)}
        onConfirm={() => revoking && revoke.mutate(revoking.id)}
      />
    </>
  )
}
