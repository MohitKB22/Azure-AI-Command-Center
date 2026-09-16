import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import {
  Badge,
  DataTable,
  ErrorState,
  LoadingPanel,
  Modal,
  PageHeader,
  Pagination,
  Panel,
  SearchInput,
  toneForStatus,
} from '@/components/ui'
import { api } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { usePagedList } from '@/lib/hooks'
import type { AuditLog } from '@/lib/types'

export function AuditPage() {
  const [action, setAction] = useState('')
  const [outcome, setOutcome] = useState('')
  const [selected, setSelected] = useState<AuditLog | null>(null)

  const actions = useQuery({ queryKey: ['audit-actions'], queryFn: () => api.get<string[]>('/audit/actions') })
  const list = usePagedList<AuditLog>(
    'audit',
    '/audit/logs',
    { action: action || undefined, outcome: outcome || undefined },
    25,
  )

  return (
    <>
      <PageHeader
        title="Audit Logs"
        description="Append-only record of every privileged action. Credential-shaped values are redacted on write."
      />

      <Panel
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <SearchInput value={list.state.search} onChange={list.state.setSearch} placeholder="Search actor or resource…" />
            <select
              className="field w-auto"
              aria-label="Filter by action"
              value={action}
              onChange={(event) => setAction(event.target.value)}
            >
              <option value="">All actions</option>
              {actions.data?.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
            <select
              className="field w-auto"
              aria-label="Filter by outcome"
              value={outcome}
              onChange={(event) => setOutcome(event.target.value)}
            >
              <option value="">All outcomes</option>
              <option value="success">Success</option>
              <option value="failure">Failure</option>
            </select>
          </div>
        }
      >
        {list.isLoading ? (
          <LoadingPanel rows={8} />
        ) : list.error ? (
          <ErrorState error={list.error} onRetry={() => list.refetch()} />
        ) : (
          <>
            <DataTable
              rows={list.data?.items ?? []}
              keyOf={(log) => log.id}
              onRowClick={setSelected}
              emptyMessage="No audit entries match these filters."
              columns={[
                {
                  key: 'action',
                  header: 'Action',
                  render: (log) => <span className="font-mono text-xs text-slate-200">{log.action}</span>,
                },
                { key: 'actor', header: 'Actor', render: (log) => log.actor_email ?? 'system' },
                {
                  key: 'resource',
                  header: 'Resource',
                  render: (log) => (
                    <span className="text-xs text-slate-400">
                      {log.resource_type}
                      {log.resource_id ? ` · ${log.resource_id.slice(0, 8)}…` : ''}
                    </span>
                  ),
                },
                {
                  key: 'outcome',
                  header: 'Outcome',
                  render: (log) => (
                    <Badge tone={log.outcome === 'success' ? 'success' : toneForStatus(log.outcome)}>{log.outcome}</Badge>
                  ),
                },
                {
                  key: 'created_at',
                  header: 'When',
                  render: (log) => <span className="text-xs text-slate-500">{formatDateTime(log.created_at)}</span>,
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

      <Modal open={Boolean(selected)} title={selected?.action ?? 'Audit entry'} onClose={() => setSelected(null)}>
        {selected && (
          <dl className="space-y-2 text-sm">
            {[
              ['Actor', selected.actor_email ?? 'system'],
              ['Resource type', selected.resource_type],
              ['Resource ID', selected.resource_id ?? '—'],
              ['Outcome', selected.outcome],
              ['Request ID', selected.request_id ?? '—'],
              ['Timestamp', formatDateTime(selected.created_at)],
            ].map(([label, value]) => (
              <div key={label} className="flex justify-between gap-3 border-b border-border/50 pb-1">
                <dt className="text-xs text-slate-400">{label}</dt>
                <dd className="truncate font-mono text-xs text-slate-200">{value}</dd>
              </div>
            ))}
            <div>
              <dt className="mb-1 text-xs text-slate-400">Changes</dt>
              <dd>
                <pre className="max-h-64 overflow-auto rounded bg-canvas p-3 text-[11px] text-slate-300">
                  {JSON.stringify(selected.changes, null, 2)}
                </pre>
              </dd>
            </div>
          </dl>
        )}
      </Modal>
    </>
  )
}
