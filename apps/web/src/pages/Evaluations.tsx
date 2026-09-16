import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import {
  Badge,
  DataTable,
  EmptyState,
  ErrorState,
  Field,
  LoadingPanel,
  Modal,
  PageHeader,
  Pagination,
  Panel,
  useToast,
} from '@/components/ui'
import { API_PREFIX, api } from '@/lib/api'
import { formatDuration, formatRelative } from '@/lib/format'
import { usePagedList } from '@/lib/hooks'
import type { Agent, Dataset, EvaluationRun, Page } from '@/lib/types'
import { useAuthStore } from '@/store/auth'

export function EvaluationsPage() {
  const queryClient = useQueryClient()
  const { notify } = useToast()
  const { can, token } = useAuthStore()

  const [datasetId, setDatasetId] = useState('')
  const [agentId, setAgentId] = useState('')
  const [threshold, setThreshold] = useState(0.5)
  const [openRunId, setOpenRunId] = useState<string | null>(null)

  const datasets = useQuery({ queryKey: ['datasets'], queryFn: () => api.get<Dataset[]>('/evaluations/datasets') })
  const agents = useQuery({
    queryKey: ['agents', 'enabled'],
    queryFn: () => api.get<Page<Agent>>('/agents?enabled=true&page_size=100'),
  })
  const metrics = useQuery({
    queryKey: ['eval-metrics'],
    queryFn: () => api.get<{ metrics: string[]; method: string; note: string }>('/evaluations/metrics'),
  })
  const runs = usePagedList<EvaluationRun>('eval-runs', '/evaluations/runs', {}, 15)

  const detail = useQuery({
    queryKey: ['eval-run', openRunId],
    queryFn: () => api.get<EvaluationRun>(`/evaluations/runs/${openRunId}`),
    enabled: Boolean(openRunId),
  })

  const start = useMutation({
    mutationFn: () =>
      api.post<EvaluationRun>('/evaluations/runs', {
        dataset_id: datasetId,
        agent_id: agentId,
        pass_threshold: threshold,
      }),
    onSuccess: (run) => {
      notify(
        run.passed ? 'Evaluation passed.' : 'Evaluation completed below threshold.',
        run.passed ? 'success' : 'warning',
      )
      queryClient.invalidateQueries({ queryKey: ['eval-runs'] })
      setOpenRunId(run.id)
    },
    onError: (error: Error) => notify(error.message, 'danger'),
  })

  async function exportCsv(runId: string) {
    const response = await fetch(`${API_PREFIX}/evaluations/runs/${runId}/export`, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    })
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `evaluation-${runId}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }

  const chartData = detail.data
    ? Object.entries(detail.data.aggregate_scores)
        .filter(([key]) => key !== 'pass_rate')
        .map(([metric, score]) => ({ metric: metric.replace(/_/g, ' '), score }))
    : []

  return (
    <>
      <PageHeader
        title="AI Evaluation"
        description="Score agents against curated datasets, track regressions and export results."
      />

      {metrics.data && (
        <div className="mb-4 rounded-md border border-border bg-surface px-3 py-2 text-xs text-slate-400">
          <strong className="text-slate-300">Method: {metrics.data.method}.</strong> {metrics.data.note}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel title="Run an evaluation">
          <div className="space-y-3">
            <Field label="Dataset">
              <select className="field" value={datasetId} onChange={(event) => setDatasetId(event.target.value)}>
                <option value="">Select a dataset…</option>
                {datasets.data?.map((dataset) => (
                  <option key={dataset.id} value={dataset.id}>
                    {dataset.name} ({dataset.items.length} items)
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Agent">
              <select className="field" value={agentId} onChange={(event) => setAgentId(event.target.value)}>
                <option value="">Select an agent…</option>
                {agents.data?.items.map((agent) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={`Pass threshold — ${threshold.toFixed(2)}`} hint="Overall score required to pass">
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={threshold}
                onChange={(event) => setThreshold(Number(event.target.value))}
                className="w-full accent-azure-500"
              />
            </Field>
            <button
              type="button"
              className="btn-primary w-full"
              disabled={!datasetId || !agentId || start.isPending || !can('evaluations:execute')}
              onClick={() => start.mutate()}
            >
              {start.isPending ? 'Evaluating…' : 'Run evaluation'}
            </button>
            <p className="text-[11px] text-slate-500">
              Each dataset item is executed as a real agent run, so evaluation consumes tokens and appears in cost
              reporting.
            </p>
          </div>
        </Panel>

        <Panel className="xl:col-span-2" title="Evaluation runs">
          {runs.isLoading ? (
            <LoadingPanel rows={5} />
          ) : runs.error ? (
            <ErrorState error={runs.error} onRetry={() => runs.refetch()} />
          ) : (
            <>
              <DataTable
                rows={runs.data?.items ?? []}
                keyOf={(run) => run.id}
                onRowClick={(run) => setOpenRunId(run.id)}
                emptyMessage="No evaluations have been run yet."
                columns={[
                  {
                    key: 'status',
                    header: 'Result',
                    render: (run) => (
                      <div className="flex flex-wrap gap-1">
                        <Badge tone={run.passed ? 'success' : 'danger'}>{run.passed ? 'passed' : 'failed'}</Badge>
                        {run.regression_detected && <Badge tone="warning">regression</Badge>}
                      </div>
                    ),
                  },
                  {
                    key: 'overall',
                    header: 'Overall',
                    render: (run) => (
                      <span className="tabular-nums text-slate-200">
                        {(run.aggregate_scores.overall ?? 0).toFixed(3)}
                      </span>
                    ),
                  },
                  {
                    key: 'grounded',
                    header: 'Groundedness',
                    render: (run) => (
                      <span className="tabular-nums">{(run.aggregate_scores.groundedness ?? 0).toFixed(3)}</span>
                    ),
                  },
                  {
                    key: 'safety',
                    header: 'Safety',
                    render: (run) => <span className="tabular-nums">{(run.aggregate_scores.safety ?? 0).toFixed(3)}</span>,
                  },
                  {
                    key: 'duration',
                    header: 'Duration',
                    render: (run) => <span className="tabular-nums">{formatDuration(run.duration_ms)}</span>,
                  },
                  {
                    key: 'created',
                    header: 'When',
                    render: (run) => <span className="text-xs text-slate-500">{formatRelative(run.created_at)}</span>,
                  },
                ]}
              />
              <Pagination
                page={runs.data?.page ?? 1}
                pages={runs.data?.pages ?? 1}
                total={runs.data?.total ?? 0}
                onChange={runs.state.setPage}
              />
            </>
          )}
        </Panel>
      </div>

      <Modal
        open={Boolean(openRunId)}
        title="Evaluation results"
        onClose={() => setOpenRunId(null)}
        wide
        footer={
          openRunId && (
            <>
              <button type="button" className="btn-ghost" onClick={() => exportCsv(openRunId)}>
                Export CSV
              </button>
              <button type="button" className="btn-ghost" onClick={() => setOpenRunId(null)}>
                Close
              </button>
            </>
          )
        }
      >
        {detail.isLoading ? (
          <LoadingPanel rows={6} />
        ) : detail.data ? (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <Badge tone={detail.data.passed ? 'success' : 'danger'}>
                {detail.data.passed ? 'passed' : 'below threshold'}
              </Badge>
              <Badge tone="neutral">threshold {detail.data.pass_threshold}</Badge>
              <Badge tone="info">pass rate {((detail.data.aggregate_scores.pass_rate ?? 0) * 100).toFixed(0)}%</Badge>
              {detail.data.regression_detected && <Badge tone="warning">regression vs previous run</Badge>}
            </div>

            {chartData.length > 0 && (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={chartData} layout="vertical" margin={{ left: 40 }}>
                  <CartesianGrid stroke="#22304d" strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" domain={[0, 1]} tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} />
                  <YAxis
                    type="category"
                    dataKey="metric"
                    width={120}
                    tick={{ fill: '#94a3b8', fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    contentStyle={{ background: '#111a2b', border: '1px solid #22304d', borderRadius: 8, fontSize: 12 }}
                  />
                  <Bar dataKey="score" fill="#1a73e8" radius={[0, 3, 3, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}

            {(detail.data.results?.length ?? 0) === 0 ? (
              <EmptyState title="No item results" />
            ) : (
              <ul className="space-y-2">
                {detail.data.results?.map((result) => (
                  <li key={result.item_index} className="rounded border border-border bg-canvas px-3 py-2">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <p className="text-xs font-medium text-slate-200">{result.question}</p>
                      <Badge tone={result.passed ? 'success' : 'danger'}>
                        {(result.scores.overall ?? 0).toFixed(3)}
                      </Badge>
                    </div>
                    <p className="mt-1 line-clamp-3 text-[11px] text-slate-400">{result.answer || '— no answer —'}</p>
                    <div className="mt-1 flex flex-wrap gap-2 text-[10px] text-slate-500">
                      {Object.entries(result.scores)
                        .filter(([key]) => key !== 'overall')
                        .map(([metric, score]) => (
                          <span key={metric}>
                            {metric.replace(/_/g, ' ')}: {score.toFixed(2)}
                          </span>
                        ))}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : null}
      </Modal>
    </>
  )
}
