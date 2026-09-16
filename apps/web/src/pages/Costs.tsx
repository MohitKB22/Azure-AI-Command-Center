import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import {
  Badge,
  DataTable,
  EmptyState,
  ErrorState,
  KpiCard,
  LoadingPanel,
  PageHeader,
  Pagination,
  Panel,
  toneForStatus,
} from '@/components/ui'
import { api } from '@/lib/api'
import { formatCurrency, formatDateTime, formatDuration, formatNumber, formatPercent } from '@/lib/format'
import { usePagedList } from '@/lib/hooks'
import type { CostSummary } from '@/lib/types'

interface UsageRecordRow {
  id: string
  run_id: string | null
  model_name: string
  team: string | null
  operation: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  estimated_cost: number
  currency: string
  latency_ms: number
  succeeded: boolean
  occurred_at: string
}

export function CostsPage() {
  const [days, setDays] = useState(30)
  const summary = useQuery({
    queryKey: ['cost-summary', days],
    queryFn: () => api.get<CostSummary>(`/costs/summary?days=${days}`),
  })
  const records = usePagedList<UsageRecordRow>('usage-records', '/costs/records', {}, 20)

  if (summary.isLoading) return <LoadingPanel rows={8} />
  if (summary.error) return <ErrorState error={summary.error} onRetry={() => summary.refetch()} />
  if (!summary.data) return null

  const { totals, timeseries, by_model, by_agent, by_team, budgets } = summary.data

  const breakdown = (
    title: string,
    rows: { key: string; requests: number; total_tokens: number; estimated_cost: number }[],
  ) => (
    <Panel title={title}>
      {rows.length === 0 ? (
        <EmptyState title="No usage in this window" />
      ) : (
        <ul className="space-y-2">
          {rows.map((row) => {
            const max = Math.max(...rows.map((item) => item.estimated_cost), 0.000001)
            return (
              <li key={row.key}>
                <div className="flex items-center justify-between text-xs">
                  <span className="truncate font-medium text-slate-200">{row.key}</span>
                  <span className="tabular-nums text-slate-400">{formatCurrency(row.estimated_cost)}</span>
                </div>
                <div className="mt-1 h-1.5 w-full rounded bg-elevated">
                  <div
                    className="h-1.5 rounded bg-azure-500"
                    style={{ width: `${Math.max(3, (row.estimated_cost / max) * 100)}%` }}
                  />
                </div>
                <p className="mt-0.5 text-[10px] text-slate-500">
                  {formatNumber(row.requests)} requests · {formatNumber(row.total_tokens)} tokens
                </p>
              </li>
            )
          })}
        </ul>
      )}
    </Panel>
  )

  return (
    <>
      <PageHeader
        title="Token & Cost Center"
        description="Spend attributed per model, agent and team, calculated from the configured per-model rates."
        actions={
          <select
            className="field w-auto"
            aria-label="Time window"
            value={days}
            onChange={(event) => setDays(Number(event.target.value))}
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="Requests" value={formatNumber(totals.requests)} />
        <KpiCard label="Total tokens" value={formatNumber(totals.total_tokens)} />
        <KpiCard label="Estimated cost" value={formatCurrency(totals.estimated_cost)} />
        <KpiCard label="Avg latency" value={formatDuration(totals.avg_latency_ms)} />
        <KpiCard label="Input tokens" value={formatNumber(totals.prompt_tokens)} />
        <KpiCard label="Output tokens" value={formatNumber(totals.completion_tokens)} />
        <KpiCard
          label="Error rate"
          value={formatPercent(totals.error_rate_pct)}
          tone={totals.error_rate_pct > 5 ? 'danger' : 'success'}
        />
        <KpiCard
          label="Cost per 1K tokens"
          value={
            totals.total_tokens > 0
              ? formatCurrency((totals.estimated_cost / totals.total_tokens) * 1000)
              : formatCurrency(0)
          }
        />
      </div>

      <Panel className="mt-4" title="Spend and tokens over time">
        <ResponsiveContainer width="100%" height={260}>
          <AreaChart data={timeseries}>
            <defs>
              <linearGradient id="cost" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.5} />
                <stop offset="100%" stopColor="#22d3ee" stopOpacity={0.03} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#22304d" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="date"
              tickFormatter={(value: string) => value.slice(5)}
              tick={{ fill: '#64748b', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis yAxisId="cost" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} width={60} />
            <YAxis
              yAxisId="tokens"
              orientation="right"
              tick={{ fill: '#64748b', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              width={60}
            />
            <Tooltip contentStyle={{ background: '#111a2b', border: '1px solid #22304d', borderRadius: 8, fontSize: 12 }} />
            <Area
              yAxisId="cost"
              type="monotone"
              dataKey="estimated_cost"
              name="Cost"
              stroke="#22d3ee"
              fill="url(#cost)"
            />
            <Area
              yAxisId="tokens"
              type="monotone"
              dataKey="total_tokens"
              name="Tokens"
              stroke="#1a73e8"
              fillOpacity={0}
            />
          </AreaChart>
        </ResponsiveContainer>
      </Panel>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        {breakdown('By model', by_model)}
        {breakdown('By agent', by_agent)}
        {breakdown('By team', by_team)}
      </div>

      <Panel className="mt-4" title="Budgets" description="Thresholds raise alerts through the worker">
        {budgets.length === 0 ? (
          <EmptyState title="No budgets configured" />
        ) : (
          <ul className="space-y-3">
            {budgets.map((budget) => (
              <li key={budget.id}>
                <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                  <span className="font-medium text-slate-200">
                    {budget.name}
                    {budget.team && <span className="ml-2 text-xs text-slate-500">{budget.team}</span>}
                  </span>
                  <span className="flex items-center gap-2 text-xs tabular-nums text-slate-400">
                    {formatCurrency(budget.spent, budget.currency)} / {formatCurrency(budget.amount, budget.currency)}
                    <Badge tone={toneForStatus(budget.state)}>{budget.state}</Badge>
                  </span>
                </div>
                <div className="mt-1 h-2 w-full rounded bg-elevated">
                  <div
                    className={`h-2 rounded ${
                      budget.state === 'exceeded' ? 'bg-danger' : budget.state === 'warning' ? 'bg-warn' : 'bg-ok'
                    }`}
                    style={{ width: `${Math.min(100, budget.utilisation_pct)}%` }}
                  />
                </div>
                <p className="mt-0.5 text-[10px] text-slate-500">{formatPercent(budget.utilisation_pct)} utilised</p>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel className="mt-4" title="Usage records" description="One row per billable model call">
        {records.isLoading ? (
          <LoadingPanel rows={5} />
        ) : (
          <>
            <DataTable
              rows={records.data?.items ?? []}
              keyOf={(record) => record.id}
              emptyMessage="No usage recorded."
              columns={[
                { key: 'model_name', header: 'Model', render: (record) => record.model_name },
                { key: 'team', header: 'Team', render: (record) => record.team ?? '—' },
                { key: 'operation', header: 'Operation', render: (record) => record.operation },
                {
                  key: 'tokens',
                  header: 'Tokens (in/out)',
                  render: (record) => (
                    <span className="font-mono text-xs tabular-nums">
                      {formatNumber(record.prompt_tokens)} / {formatNumber(record.completion_tokens)}
                    </span>
                  ),
                },
                {
                  key: 'cost',
                  header: 'Cost',
                  render: (record) => (
                    <span className="tabular-nums">{formatCurrency(record.estimated_cost, record.currency)}</span>
                  ),
                },
                {
                  key: 'latency',
                  header: 'Latency',
                  render: (record) => <span className="tabular-nums">{formatDuration(record.latency_ms)}</span>,
                },
                {
                  key: 'succeeded',
                  header: 'Result',
                  render: (record) => (
                    <Badge tone={record.succeeded ? 'success' : 'danger'}>{record.succeeded ? 'ok' : 'error'}</Badge>
                  ),
                },
                {
                  key: 'occurred_at',
                  header: 'When',
                  render: (record) => <span className="text-xs text-slate-500">{formatDateTime(record.occurred_at)}</span>,
                },
              ]}
            />
            <Pagination
              page={records.data?.page ?? 1}
              pages={records.data?.pages ?? 1}
              total={records.data?.total ?? 0}
              onChange={records.state.setPage}
            />
          </>
        )}
      </Panel>
    </>
  )
}
