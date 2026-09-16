import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { Link, useParams } from 'react-router-dom'

import {
  Badge,
  EmptyState,
  ErrorState,
  LoadingPanel,
  PageHeader,
  Panel,
  StatusDot,
  toneForStatus,
} from '@/components/ui'
import { api } from '@/lib/api'
import { formatCurrency, formatDateTime, formatDuration, formatNumber, titleCase } from '@/lib/format'
import type { RunDetail } from '@/lib/types'

export function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>()
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['run', runId],
    queryFn: () => api.get<RunDetail>(`/runs/${runId}`),
    enabled: Boolean(runId),
  })

  if (isLoading) return <LoadingPanel rows={10} />
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />
  if (!data) return null

  const totalDuration = data.steps.reduce((sum, step) => sum + step.duration_ms, 0) || 1

  return (
    <>
      <PageHeader
        title="Run inspector"
        description={`Run ${data.id}`}
        actions={
          <>
            <Badge tone={toneForStatus(data.status)}>
              <StatusDot status={data.status} /> {data.status}
            </Badge>
            <Link className="btn-ghost" to={`/agents/${data.agent_id}`}>
              Open agent
            </Link>
            <Link className="btn-ghost" to="/runs">
              Back
            </Link>
          </>
        }
      />

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel title="Summary">
          <dl className="space-y-2 text-sm">
            {[
              ['Agent version', `v${data.agent_version}`],
              ['Model', data.model_name ?? '—'],
              ['Fallback used', data.used_fallback ? 'yes' : 'no'],
              ['Prompt tokens', formatNumber(data.prompt_tokens)],
              ['Completion tokens', formatNumber(data.completion_tokens)],
              ['Total tokens', formatNumber(data.total_tokens)],
              ['Estimated cost', formatCurrency(data.estimated_cost)],
              ['Latency', formatDuration(data.latency_ms)],
              ['Guardrail', data.guardrail_outcome],
              ['Evaluation score', data.evaluation_score?.toFixed(3) ?? '—'],
              ['Correlation ID', data.correlation_id ?? '—'],
              ['Started', formatDateTime(data.created_at)],
            ].map(([label, value]) => (
              <div key={label} className="flex items-center justify-between gap-3 border-b border-border/50 pb-1">
                <dt className="text-xs text-slate-400">{label}</dt>
                <dd className="truncate font-mono text-xs text-slate-200">{value}</dd>
              </div>
            ))}
          </dl>
          {data.error_message && (
            <div className="mt-3 rounded border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-red-200">
              <p className="font-medium">{data.error_code}</p>
              <p className="mt-1">{data.error_message}</p>
            </div>
          )}
        </Panel>

        <Panel title="Execution graph" description="Each node with its duration" className="xl:col-span-2">
          <ol className="space-y-2">
            {data.steps.map((step) => (
              <li key={step.step_index} className="rounded-md border border-border bg-canvas px-3 py-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="flex items-center gap-2">
                    <span className="grid h-5 w-5 place-items-center rounded bg-elevated text-[10px] text-slate-400">
                      {step.step_index + 1}
                    </span>
                    <span className="text-sm font-medium text-slate-200">{titleCase(step.node)}</span>
                    <Badge tone={toneForStatus(step.status)}>{step.status}</Badge>
                  </span>
                  <span className="tabular-nums text-[11px] text-slate-500">{step.duration_ms} ms</span>
                </div>
                <div className="mt-1.5 h-1 w-full rounded bg-elevated">
                  <div
                    className={clsx(
                      'h-1 rounded',
                      step.status === 'ok' ? 'bg-azure-500' : step.status === 'skipped' ? 'bg-slate-600' : 'bg-warn',
                    )}
                    style={{ width: `${Math.max(2, (step.duration_ms / totalDuration) * 100)}%` }}
                  />
                </div>
                {Object.keys(step.detail ?? {}).length > 0 && (
                  <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
                    {Object.entries(step.detail).map(([key, value]) => (
                      <div key={key} className="text-[11px]">
                        <dt className="inline text-slate-500">{key}: </dt>
                        <dd className="inline font-mono text-slate-300">
                          {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                        </dd>
                      </div>
                    ))}
                  </dl>
                )}
              </li>
            ))}
          </ol>
        </Panel>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Panel title="Input">
          <pre className="whitespace-pre-wrap break-words rounded bg-canvas p-3 text-xs text-slate-300">
            {data.input_text}
          </pre>
        </Panel>
        <Panel title="Output">
          {data.output_text ? (
            <pre className="whitespace-pre-wrap break-words rounded bg-canvas p-3 text-xs text-slate-300">
              {data.output_text}
            </pre>
          ) : (
            <EmptyState title="No output produced" description="The run was blocked or failed before generation." />
          )}
        </Panel>
      </div>

      <Panel className="mt-4" title="Retrieved documents" description="Sources used to ground this answer">
        {data.citations.length === 0 ? (
          <EmptyState
            title="No sources retrieved"
            description="Either retrieval was skipped or nothing passed the similarity threshold."
          />
        ) : (
          <ol className="space-y-2">
            {data.citations.map((citation, index) => (
              <li key={citation.chunk_id} className="rounded-md border border-border bg-canvas px-3 py-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm text-slate-200">
                    [{index + 1}] {citation.document_name}
                    {citation.page ? ` · page ${citation.page}` : ''}
                  </span>
                  <Badge tone="info">score {citation.score.toFixed(3)}</Badge>
                </div>
                <p className="mt-1 text-xs text-slate-400">{citation.snippet}</p>
              </li>
            ))}
          </ol>
        )}
      </Panel>

      <Panel className="mt-4" title="Trace metadata" description="Providers, routing and retrieval configuration">
        <pre className="max-h-80 overflow-auto rounded bg-canvas p-3 text-[11px] leading-relaxed text-slate-400">
          {JSON.stringify(data.trace, null, 2)}
        </pre>
        <p className="mt-2 text-[11px] text-slate-500">
          Secrets are never written to a trace — the logger redacts credential-shaped values on write.
        </p>
      </Panel>
    </>
  )
}
