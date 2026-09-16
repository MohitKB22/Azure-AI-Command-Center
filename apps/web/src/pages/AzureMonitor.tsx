import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  Badge,
  DataTable,
  ErrorState,
  LoadingPanel,
  PageHeader,
  Panel,
  StatusDot,
  toneForStatus,
  useToast,
} from '@/components/ui'
import { api } from '@/lib/api'
import { formatDuration, formatPercent, formatRelative } from '@/lib/format'
import type { AzureResource, SystemHealth } from '@/lib/types'
import { useAuthStore } from '@/store/auth'

export function AzureMonitorPage() {
  const queryClient = useQueryClient()
  const { notify } = useToast()
  const can = useAuthStore((state) => state.can)

  const resources = useQuery({
    queryKey: ['azure-resources'],
    queryFn: () => api.get<AzureResource[]>('/monitoring/azure-resources'),
    refetchInterval: 60_000,
  })
  const health = useQuery({
    queryKey: ['system-health'],
    queryFn: () => api.get<SystemHealth>('/monitoring/health'),
    refetchInterval: 30_000,
  })

  const collect = useMutation({
    mutationFn: () => api.post<AzureResource[]>('/monitoring/collect'),
    onSuccess: () => {
      notify('Collector run complete.', 'success')
      queryClient.invalidateQueries({ queryKey: ['azure-resources'] })
      queryClient.invalidateQueries({ queryKey: ['system-health'] })
    },
    onError: (error: Error) => notify(error.message, 'danger'),
  })

  const notConfigured = (resources.data ?? []).filter((r) => r.data_source === 'none').length

  return (
    <>
      <PageHeader
        title="Azure Service Monitor"
        description="Availability, latency, errors and throughput for the platform's Azure dependencies."
        actions={
          can('monitoring:write') && (
            <button type="button" className="btn-primary" disabled={collect.isPending} onClick={() => collect.mutate()}>
              {collect.isPending ? 'Collecting…' : 'Run collector'}
            </button>
          )
        }
      />

      {notConfigured > 0 && (
        <div className="mb-4 rounded-md border border-warn/40 bg-warn/10 px-3 py-2 text-xs text-amber-200">
          <strong className="font-semibold">{notConfigured} resource(s) report `not_configured`.</strong> No Azure
          credentials are present, so no metrics are collected for them. The platform deliberately shows zeros rather
          than synthesising plausible-looking values.
        </div>
      )}

      <Panel title="System components" description="Checks the API performs against its own dependencies">
        {health.isLoading ? (
          <LoadingPanel rows={3} />
        ) : health.error ? (
          <ErrorState error={health.error} onRetry={() => health.refetch()} />
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {health.data?.components.map((component) => (
                <div key={component.component} className="rounded-md border border-border bg-canvas px-3 py-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-slate-200">{component.component}</span>
                    <Badge tone={toneForStatus(component.status)}>
                      <StatusDot status={component.status} /> {component.status}
                    </Badge>
                  </div>
                  <p className="mt-1 text-[11px] text-slate-500">{component.detail || '—'}</p>
                  <p className="mt-1 text-[11px] text-slate-600">
                    {component.latency_ms} ms · source {component.data_source}
                  </p>
                </div>
              ))}
            </div>
            <dl className="mt-3 flex flex-wrap gap-4 text-[11px] text-slate-400">
              <div>
                <dt className="inline">Uptime: </dt>
                <dd className="inline text-slate-200">{formatDuration((health.data?.uptime_seconds ?? 0) * 1000)}</dd>
              </div>
              <div>
                <dt className="inline">Requests (24h): </dt>
                <dd className="inline text-slate-200">{health.data?.requests_24h}</dd>
              </div>
              <div>
                <dt className="inline">Error rate (24h): </dt>
                <dd className="inline text-slate-200">{formatPercent(health.data?.error_rate_24h_pct)}</dd>
              </div>
              <div>
                <dt className="inline">Python: </dt>
                <dd className="inline text-slate-200">{health.data?.python}</dd>
              </div>
            </dl>
          </>
        )}
      </Panel>

      <Panel className="mt-4" title="Azure resources">
        {resources.isLoading ? (
          <LoadingPanel rows={6} />
        ) : resources.error ? (
          <ErrorState error={resources.error} onRetry={() => resources.refetch()} />
        ) : (
          <DataTable
            rows={resources.data ?? []}
            keyOf={(resource) => resource.id}
            emptyMessage="No Azure resources registered."
            columns={[
              {
                key: 'name',
                header: 'Resource',
                render: (resource) => (
                  <div className="flex items-start gap-2">
                    <StatusDot status={resource.status} />
                    <div>
                      <p className="font-medium text-slate-100">{resource.name}</p>
                      <p className="font-mono text-[11px] text-slate-500">{resource.resource_type}</p>
                    </div>
                  </div>
                ),
              },
              { key: 'region', header: 'Region', render: (resource) => resource.region },
              {
                key: 'status',
                header: 'Status',
                render: (resource) => (
                  <div className="flex flex-col gap-1">
                    <Badge tone={toneForStatus(resource.status)}>{resource.status}</Badge>
                    <span className="text-[10px] text-slate-500">source: {resource.data_source}</span>
                  </div>
                ),
              },
              {
                key: 'availability',
                header: 'Availability',
                render: (resource) =>
                  resource.data_source === 'none' ? (
                    <span className="text-slate-600">no data</span>
                  ) : (
                    <span className="tabular-nums">{formatPercent(resource.availability_pct)}</span>
                  ),
              },
              {
                key: 'latency',
                header: 'p95 latency',
                render: (resource) =>
                  resource.data_source === 'none' ? (
                    <span className="text-slate-600">no data</span>
                  ) : (
                    <span className="tabular-nums">{formatDuration(resource.latency_p95_ms)}</span>
                  ),
              },
              {
                key: 'errors',
                header: 'Error rate',
                render: (resource) =>
                  resource.data_source === 'none' ? (
                    <span className="text-slate-600">no data</span>
                  ) : (
                    <span className="tabular-nums">{formatPercent(resource.error_rate_pct)}</span>
                  ),
              },
              {
                key: 'checked',
                header: 'Checked',
                render: (resource) => (
                  <span className="text-xs text-slate-500">{formatRelative(resource.last_checked_at)}</span>
                ),
              },
            ]}
          />
        )}
        <p className="mt-3 text-[11px] leading-relaxed text-slate-500">
          <strong className="text-slate-400">Data sources.</strong> <code>local</code> means the value was measured by
          this platform (its own database, storage, or recent usage records). <code>live</code> means it came from Azure
          Monitor. <code>none</code> means the resource is registered but unmonitored — no value is invented for it.
        </p>
      </Panel>
    </>
  )
}
