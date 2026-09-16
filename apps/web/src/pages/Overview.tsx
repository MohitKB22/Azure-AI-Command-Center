import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import {
  Badge,
  DemoBanner,
  EmptyState,
  ErrorState,
  KpiCard,
  LoadingPanel,
  PageHeader,
  Panel,
  StatusDot,
  toneForStatus,
} from '@/components/ui'
import { api } from '@/lib/api'
import { formatCurrency, formatDuration, formatNumber, formatPercent, formatRelative } from '@/lib/format'
import type { Overview } from '@/lib/types'

const AXIS = { stroke: '#64748b', fontSize: 11 }
const GRID = '#22304d'

const chartTooltip = {
  contentStyle: {
    background: '#111a2b',
    border: '1px solid #22304d',
    borderRadius: 8,
    fontSize: 12,
  },
  labelStyle: { color: '#cbd5e1' },
}

export function OverviewPage() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['overview'],
    queryFn: () => api.get<Overview>('/overview?days=14'),
    refetchInterval: 60_000,
  })

  if (isLoading) return <LoadingPanel rows={8} />
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />
  if (!data) return null

  const { kpis, timeseries, health } = data
  const shortDate = (value: string) => value.slice(5)

  return (
    <>
      <PageHeader
        title="Overview"
        description={`Platform activity for the last ${kpis.window_days} days. Generated ${formatRelative(
          data.generated_at,
        )}.`}
        actions={
          <>
            <Badge tone={health.status === 'healthy' ? 'success' : 'warning'}>
              <StatusDot status={health.status} /> {health.status}
            </Badge>
            <Badge tone="info">llm: {data.providers.llm}</Badge>
            <Badge tone="info">vectors: {data.providers.vector_store}</Badge>
          </>
        }
      />

      <DemoBanner show={data.demo_mode} />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Active agents"
          value={formatNumber(kpis.active_agents)}
          hint={`${formatNumber(kpis.total_agents)} registered`}
        />
        <KpiCard label="Requests" value={formatNumber(kpis.total_requests)} hint={`${formatNumber(kpis.agent_runs)} agent runs`} />
        <KpiCard label="Tokens" value={formatNumber(kpis.total_tokens)} />
        <KpiCard label="Estimated cost" value={formatCurrency(kpis.estimated_cost)} />
        <KpiCard label="Avg latency" value={formatDuration(kpis.avg_latency_ms)} />
        <KpiCard
          label="Error rate"
          value={formatPercent(kpis.error_rate_pct)}
          tone={kpis.error_rate_pct > 5 ? 'danger' : 'success'}
          hint={kpis.error_rate_pct > 5 ? 'above threshold' : 'within threshold'}
        />
        <KpiCard
          label="Grounded answers"
          value={formatPercent(kpis.rag_grounded_pct)}
          hint="runs returning citations"
          tone={kpis.rag_grounded_pct > 80 ? 'success' : 'warning'}
        />
        <KpiCard
          label="Indexed documents"
          value={formatNumber(kpis.indexed_documents)}
          hint={`${formatNumber(kpis.active_alerts)} active alerts`}
          tone={kpis.active_alerts > 0 ? 'warning' : 'success'}
        />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Panel title="Requests and tokens" description="Daily volume across all agents">
          {timeseries.length === 0 ? (
            <EmptyState title="No usage recorded yet" description="Run an agent to populate this chart." />
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={timeseries}>
                <defs>
                  <linearGradient id="tokens" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#1a73e8" stopOpacity={0.55} />
                    <stop offset="100%" stopColor="#1a73e8" stopOpacity={0.03} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tickFormatter={shortDate} tick={AXIS} tickLine={false} axisLine={false} />
                <YAxis tick={AXIS} tickLine={false} axisLine={false} width={54} />
                <Tooltip {...chartTooltip} />
                <Area type="monotone" dataKey="total_tokens" name="Tokens" stroke="#1a73e8" fill="url(#tokens)" />
                <Line type="monotone" dataKey="requests" name="Requests" stroke="#22d3ee" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </Panel>

        <Panel title="Cost over time" description="Estimated spend per day">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={timeseries}>
              <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="date" tickFormatter={shortDate} tick={AXIS} tickLine={false} axisLine={false} />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={54} />
              <Tooltip {...chartTooltip} formatter={(value: number) => formatCurrency(value)} />
              <Bar dataKey="estimated_cost" name="Cost" radius={[3, 3, 0, 0]}>
                {timeseries.map((point) => (
                  <Cell key={point.date} fill="#0f5bc4" />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Latency and error rate" description="Average latency with failure percentage">
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={timeseries}>
              <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="date" tickFormatter={shortDate} tick={AXIS} tickLine={false} axisLine={false} />
              <YAxis yAxisId="left" tick={AXIS} tickLine={false} axisLine={false} width={54} />
              <YAxis yAxisId="right" orientation="right" tick={AXIS} tickLine={false} axisLine={false} width={40} />
              <Tooltip {...chartTooltip} />
              <Line yAxisId="left" type="monotone" dataKey="avg_latency_ms" name="Latency (ms)" stroke="#63a6ff" dot={false} />
              <Line yAxisId="right" type="monotone" dataKey="error_rate_pct" name="Errors (%)" stroke="#ef4444" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Model utilisation" description="Requests and cost by model">
          {data.model_usage.length === 0 ? (
            <EmptyState title="No model usage yet" />
          ) : (
            <ul className="space-y-2">
              {data.model_usage.map((row) => {
                const max = Math.max(...data.model_usage.map((item) => item.total_tokens), 1)
                return (
                  <li key={row.key}>
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium text-slate-200">{row.key}</span>
                      <span className="tabular-nums text-slate-400">
                        {formatNumber(row.requests)} req · {formatCurrency(row.estimated_cost)}
                      </span>
                    </div>
                    <div className="mt-1 h-1.5 w-full rounded bg-elevated">
                      <div
                        className="h-1.5 rounded bg-azure-500"
                        style={{ width: `${Math.max(3, (row.total_tokens / max) * 100)}%` }}
                      />
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </Panel>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Panel
          title="Recent agent runs"
          className="xl:col-span-2"
          actions={
            <Link className="btn-ghost px-2 py-1 text-xs" to="/runs">
              View all
            </Link>
          }
        >
          {data.recent_runs.length === 0 ? (
            <EmptyState title="No runs yet" description="Open an agent and run it to see traces here." />
          ) : (
            <ul className="divide-y divide-border/60">
              {data.recent_runs.map((run) => (
                <li key={run.id}>
                  <Link to={`/runs/${run.id}`} className="flex items-center justify-between gap-3 py-2 hover:text-white">
                    <span className="flex min-w-0 items-center gap-2">
                      <StatusDot status={run.status} />
                      <span className="truncate text-sm text-slate-300">{run.model_name ?? 'unknown model'}</span>
                      <Badge tone={toneForStatus(run.guardrail_outcome)}>{run.guardrail_outcome}</Badge>
                    </span>
                    <span className="shrink-0 text-xs tabular-nums text-slate-500">
                      {formatNumber(run.total_tokens)} tok · {formatDuration(run.latency_ms)} ·{' '}
                      {formatRelative(run.created_at)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel
          title="Active alerts"
          actions={
            <Link className="btn-ghost px-2 py-1 text-xs" to="/alerts">
              Manage
            </Link>
          }
        >
          {data.active_alerts.length === 0 ? (
            <EmptyState title="No active alerts" description="Nothing needs attention right now." />
          ) : (
            <ul className="space-y-3">
              {data.active_alerts.map((alert) => (
                <li key={alert.id} className="rounded-md border border-border bg-canvas px-3 py-2">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm text-slate-200">{alert.title}</p>
                    <Badge tone={toneForStatus(alert.severity)}>{alert.severity}</Badge>
                  </div>
                  <p className="mt-1 text-[11px] text-slate-500">
                    {alert.source} · {formatRelative(alert.created_at)}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <Panel className="mt-4" title="System health" description="Live component checks">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {health.components.map((component) => (
            <div key={component.component} className="rounded-md border border-border bg-canvas px-3 py-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-200">{component.component}</span>
                <Badge tone={toneForStatus(component.status)}>{component.status}</Badge>
              </div>
              <p className="mt-1 line-clamp-2 text-[11px] text-slate-500">{component.detail || '—'}</p>
              <p className="mt-1 text-[11px] text-slate-600">
                source: {component.data_source} · {component.latency_ms} ms
              </p>
            </div>
          ))}
        </div>
        {health.configuration_warnings.length > 0 && (
          <ul className="mt-3 space-y-1 rounded-md border border-warn/40 bg-warn/10 px-3 py-2 text-xs text-amber-200">
            {health.configuration_warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        )}
      </Panel>
    </>
  )
}
