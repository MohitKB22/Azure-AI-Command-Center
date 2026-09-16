import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  Badge,
  DataTable,
  ErrorState,
  LoadingPanel,
  PageHeader,
  Pagination,
  Panel,
  SearchInput,
  StatusDot,
  toneForStatus,
  useToast,
} from '@/components/ui'
import { api } from '@/lib/api'
import { formatRelative } from '@/lib/format'
import { usePagedList } from '@/lib/hooks'
import type { Alert } from '@/lib/types'
import { useAuthStore } from '@/store/auth'

export function AlertsPage() {
  const queryClient = useQueryClient()
  const { notify } = useToast()
  const can = useAuthStore((state) => state.can)
  const [statusFilter, setStatusFilter] = useState('active')
  const [severity, setSeverity] = useState('')

  const list = usePagedList<Alert>(
    'alerts',
    '/monitoring/alerts',
    { status_filter: statusFilter || undefined, severity: severity || undefined },
    20,
  )

  const act = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'acknowledge' | 'resolve' }) =>
      api.post<Alert>(`/monitoring/alerts/${id}/${action}`),
    onSuccess: (_data, variables) => {
      notify(`Alert ${variables.action}d.`, 'success')
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
      queryClient.invalidateQueries({ queryKey: ['overview'] })
    },
    onError: (error: Error) => notify(error.message, 'danger'),
  })

  return (
    <>
      <PageHeader title="Alerts" description="Operational signals raised by the platform and its background worker." />

      <Panel
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <SearchInput value={list.state.search} onChange={list.state.setSearch} placeholder="Search alerts…" />
            <select
              className="field w-auto"
              aria-label="Filter by status"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option value="">All statuses</option>
              <option value="active">Active</option>
              <option value="acknowledged">Acknowledged</option>
              <option value="resolved">Resolved</option>
            </select>
            <select
              className="field w-auto"
              aria-label="Filter by severity"
              value={severity}
              onChange={(event) => setSeverity(event.target.value)}
            >
              <option value="">All severities</option>
              <option value="critical">Critical</option>
              <option value="warning">Warning</option>
              <option value="info">Info</option>
            </select>
          </div>
        }
      >
        {list.isLoading ? (
          <LoadingPanel rows={5} />
        ) : list.error ? (
          <ErrorState error={list.error} onRetry={() => list.refetch()} />
        ) : (
          <>
            <DataTable
              rows={list.data?.items ?? []}
              keyOf={(alert) => alert.id}
              emptyMessage="No alerts match these filters."
              columns={[
                {
                  key: 'title',
                  header: 'Alert',
                  render: (alert) => (
                    <div className="flex items-start gap-2">
                      <StatusDot status={alert.severity} />
                      <div className="min-w-0">
                        <p className="font-medium text-slate-100">{alert.title}</p>
                        <p className="text-xs text-slate-500">{alert.description ?? '—'}</p>
                      </div>
                    </div>
                  ),
                },
                {
                  key: 'severity',
                  header: 'Severity',
                  render: (alert) => <Badge tone={toneForStatus(alert.severity)}>{alert.severity}</Badge>,
                },
                { key: 'source', header: 'Source', render: (alert) => alert.source },
                {
                  key: 'status',
                  header: 'Status',
                  render: (alert) => <Badge tone={toneForStatus(alert.status)}>{alert.status}</Badge>,
                },
                {
                  key: 'created_at',
                  header: 'Raised',
                  render: (alert) => <span className="text-xs text-slate-500">{formatRelative(alert.created_at)}</span>,
                },
                {
                  key: 'actions',
                  header: '',
                  render: (alert) =>
                    can('monitoring:write') ? (
                      <div className="flex justify-end gap-1">
                        {alert.status === 'active' && (
                          <button
                            type="button"
                            className="btn-ghost px-2 py-1 text-[11px]"
                            onClick={() => act.mutate({ id: alert.id, action: 'acknowledge' })}
                          >
                            Acknowledge
                          </button>
                        )}
                        {alert.status !== 'resolved' && (
                          <button
                            type="button"
                            className="btn-ghost px-2 py-1 text-[11px]"
                            onClick={() => act.mutate({ id: alert.id, action: 'resolve' })}
                          >
                            Resolve
                          </button>
                        )}
                      </div>
                    ) : null,
                  className: 'text-right',
                },
              ]}
            />
            <Pagination
              page={list.data?.page ?? 1}
              pages={list.data?.pages ?? 1}
              total={list.data?.total ?? 0}
              onChange={list.state.setPage}
            />
          </>
        )}
      </Panel>
    </>
  )
}
