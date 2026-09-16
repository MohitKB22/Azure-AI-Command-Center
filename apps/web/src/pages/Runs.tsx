import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

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
} from '@/components/ui'
import { formatCurrency, formatDuration, formatNumber, formatRelative } from '@/lib/format'
import { usePagedList } from '@/lib/hooks'
import type { RunSummary } from '@/lib/types'

export function RunsPage() {
  const navigate = useNavigate()
  const [statusFilter, setStatusFilter] = useState('')
  const list = usePagedList<RunSummary>('runs', '/runs', { status_filter: statusFilter || undefined }, 25)

  return (
    <>
      <PageHeader
        title="Agent Runs"
        description="Every execution with its trace, tokens, cost, guardrail outcome and citations."
      />

      <Panel
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <SearchInput value={list.state.search} onChange={list.state.setSearch} placeholder="Search input/output…" />
            <select
              className="field w-auto"
              aria-label="Filter by status"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option value="">All statuses</option>
              <option value="succeeded">Succeeded</option>
              <option value="blocked">Blocked</option>
              <option value="failed">Failed</option>
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
              keyOf={(run) => run.id}
              onRowClick={(run) => navigate(`/runs/${run.id}`)}
              sortBy={list.state.sortBy}
              sortDir={list.state.sortDir}
              onSort={list.state.toggleSort}
              emptyMessage="No runs recorded yet."
              columns={[
                {
                  key: 'status',
                  header: 'Status',
                  sortable: true,
                  render: (run) => (
                    <span className="flex items-center gap-2">
                      <StatusDot status={run.status} />
                      <Badge tone={toneForStatus(run.status)}>{run.status}</Badge>
                    </span>
                  ),
                },
                {
                  key: 'model_name',
                  header: 'Model',
                  sortable: true,
                  render: (run) => (
                    <span className="flex items-center gap-1 text-slate-300">
                      {run.model_name ?? '—'}
                      {run.used_fallback && <Badge tone="warning">fallback</Badge>}
                    </span>
                  ),
                },
                {
                  key: 'total_tokens',
                  header: 'Tokens',
                  sortable: true,
                  render: (run) => <span className="tabular-nums">{formatNumber(run.total_tokens)}</span>,
                },
                {
                  key: 'estimated_cost',
                  header: 'Cost',
                  sortable: true,
                  render: (run) => <span className="tabular-nums">{formatCurrency(run.estimated_cost)}</span>,
                },
                {
                  key: 'latency_ms',
                  header: 'Latency',
                  sortable: true,
                  render: (run) => <span className="tabular-nums">{formatDuration(run.latency_ms)}</span>,
                },
                {
                  key: 'guardrail_outcome',
                  header: 'Guardrail',
                  render: (run) => <Badge tone={toneForStatus(run.guardrail_outcome)}>{run.guardrail_outcome}</Badge>,
                },
                {
                  key: 'evaluation_score',
                  header: 'Eval',
                  render: (run) =>
                    run.evaluation_score === null ? (
                      <span className="text-slate-600">—</span>
                    ) : (
                      <span className="tabular-nums">{run.evaluation_score.toFixed(2)}</span>
                    ),
                },
                {
                  key: 'created_at',
                  header: 'When',
                  sortable: true,
                  render: (run) => <span className="text-xs text-slate-500">{formatRelative(run.created_at)}</span>,
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
