import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import {
  Badge,
  ConfirmDialog,
  DataTable,
  EmptyState,
  ErrorState,
  Field,
  LoadingPanel,
  PageHeader,
  Panel,
  StatusDot,
  toneForStatus,
  useToast,
} from '@/components/ui'
import { api } from '@/lib/api'
import { formatDateTime, formatDuration, formatNumber, formatRelative } from '@/lib/format'
import type {
  AgentDetail,
  GuardrailPolicy,
  ModelEntry,
  Page,
  Pipeline,
  RunDetail,
  RunSummary,
} from '@/lib/types'
import { useAuthStore } from '@/store/auth'

interface AgentVersion {
  id: string
  version: number
  changelog: string | null
  snapshot: Record<string, unknown>
  created_at: string
}

export function AgentDetailPage() {
  const { agentId } = useParams<{ agentId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { notify } = useToast()
  const can = useAuthStore((state) => state.can)

  const [form, setForm] = useState<Partial<AgentDetail>>({})
  const [testInput, setTestInput] = useState('What is the default chunk size and overlap?')
  const [lastRun, setLastRun] = useState<RunDetail | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const agent = useQuery({
    queryKey: ['agent', agentId],
    queryFn: () => api.get<AgentDetail>(`/agents/${agentId}`),
    enabled: Boolean(agentId),
  })

  const models = useQuery({
    queryKey: ['models', 'chat'],
    queryFn: () => api.get<Page<ModelEntry>>('/models?kind=chat&page_size=100'),
  })
  const pipelines = useQuery({ queryKey: ['pipelines'], queryFn: () => api.get<Pipeline[]>('/rag/pipelines') })
  const policies = useQuery({
    queryKey: ['policies'],
    queryFn: () => api.get<GuardrailPolicy[]>('/guardrails/policies'),
  })
  const versions = useQuery({
    queryKey: ['agent-versions', agentId],
    queryFn: () => api.get<AgentVersion[]>(`/agents/${agentId}/versions`),
    enabled: Boolean(agentId),
  })
  const runs = useQuery({
    queryKey: ['agent-runs', agentId],
    queryFn: () => api.get<Page<RunSummary>>(`/runs?agent_id=${agentId}&page_size=10`),
    enabled: Boolean(agentId),
  })

  useEffect(() => {
    if (agent.data) setForm(agent.data)
  }, [agent.data])

  const save = useMutation({
    mutationFn: () =>
      api.patch<AgentDetail>(`/agents/${agentId}`, {
        name: form.name,
        description: form.description,
        system_prompt: form.system_prompt,
        model_id: form.model_id,
        fallback_model_id: form.fallback_model_id,
        temperature: form.temperature,
        max_output_tokens: form.max_output_tokens,
        timeout_seconds: form.timeout_seconds,
        max_retries: form.max_retries,
        rag_enabled: form.rag_enabled,
        rag_pipeline_id: form.rag_pipeline_id,
        guardrail_policy_id: form.guardrail_policy_id,
        status: form.status,
        environment: form.environment,
      }),
    onSuccess: () => {
      notify('Agent saved. A new version was recorded.', 'success')
      queryClient.invalidateQueries({ queryKey: ['agent', agentId] })
      queryClient.invalidateQueries({ queryKey: ['agent-versions', agentId] })
    },
    onError: (error: Error) => notify(error.message, 'danger'),
  })

  const toggle = useMutation({
    mutationFn: () => api.post<AgentDetail>(`/agents/${agentId}/toggle`),
    onSuccess: (updated) => {
      notify(updated.enabled ? 'Agent enabled.' : 'Agent disabled.', 'info')
      queryClient.invalidateQueries({ queryKey: ['agent', agentId] })
    },
  })

  const run = useMutation({
    mutationFn: () => api.post<RunDetail>(`/agents/${agentId}/run`, { input: testInput }),
    onSuccess: (result) => {
      setLastRun(result)
      queryClient.invalidateQueries({ queryKey: ['agent-runs', agentId] })
      notify(`Run ${result.status}.`, result.status === 'succeeded' ? 'success' : 'warning')
    },
    onError: (error: Error) => notify(error.message, 'danger'),
  })

  const rollback = useMutation({
    mutationFn: (version: number) => api.post<AgentDetail>(`/agents/${agentId}/versions/${version}/rollback`),
    onSuccess: () => {
      notify('Rolled back.', 'success')
      queryClient.invalidateQueries({ queryKey: ['agent', agentId] })
      queryClient.invalidateQueries({ queryKey: ['agent-versions', agentId] })
    },
    onError: (error: Error) => notify(error.message, 'danger'),
  })

  const remove = useMutation({
    mutationFn: () => api.delete(`/agents/${agentId}`),
    onSuccess: () => {
      notify('Agent archived.', 'info')
      navigate('/agents')
    },
  })

  if (agent.isLoading) return <LoadingPanel rows={10} />
  if (agent.error) return <ErrorState error={agent.error} onRetry={() => agent.refetch()} />
  if (!agent.data) return null

  const editable = can('agents:write')

  return (
    <>
      <PageHeader
        title={agent.data.name}
        description={agent.data.description ?? `Slug: ${agent.data.slug}`}
        actions={
          <>
            <Badge tone={toneForStatus(agent.data.status)}>
              <StatusDot status={agent.data.status} /> {agent.data.status}
            </Badge>
            <Badge tone="info">v{agent.data.current_version}</Badge>
            <Link className="btn-ghost" to="/agents">
              Back
            </Link>
            {editable && (
              <button type="button" className="btn-ghost" onClick={() => toggle.mutate()}>
                {agent.data.enabled ? 'Disable' : 'Enable'}
              </button>
            )}
            {can('agents:delete') && (
              <button type="button" className="btn-danger" onClick={() => setConfirmDelete(true)}>
                Archive
              </button>
            )}
          </>
        }
      />

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel
          title="Configuration"
          className="xl:col-span-2"
          actions={
            editable && (
              <button type="button" className="btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>
                {save.isPending ? 'Saving…' : 'Save changes'}
              </button>
            )
          }
        >
          <fieldset disabled={!editable} className="grid gap-4 sm:grid-cols-2">
            <Field label="Name">
              <input
                className="field"
                value={form.name ?? ''}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
              />
            </Field>
            <Field label="Status">
              <select
                className="field"
                value={form.status ?? 'draft'}
                onChange={(event) => setForm({ ...form, status: event.target.value })}
              >
                <option value="draft">Draft</option>
                <option value="active">Active</option>
                <option value="paused">Paused</option>
                <option value="archived">Archived</option>
              </select>
            </Field>
            <Field label="Model">
              <select
                className="field"
                value={form.model_id ?? ''}
                onChange={(event) => setForm({ ...form, model_id: event.target.value || null })}
              >
                <option value="">None</option>
                {models.data?.items.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Fallback model">
              <select
                className="field"
                value={form.fallback_model_id ?? ''}
                onChange={(event) => setForm({ ...form, fallback_model_id: event.target.value || null })}
              >
                <option value="">None</option>
                {models.data?.items.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Temperature" hint="0 is deterministic, 2 is maximally varied">
              <input
                type="number"
                step="0.1"
                min={0}
                max={2}
                className="field"
                value={form.temperature ?? 0.2}
                onChange={(event) => setForm({ ...form, temperature: Number(event.target.value) })}
              />
            </Field>
            <Field label="Max output tokens">
              <input
                type="number"
                min={1}
                className="field"
                value={form.max_output_tokens ?? 800}
                onChange={(event) => setForm({ ...form, max_output_tokens: Number(event.target.value) })}
              />
            </Field>
            <Field label="Timeout (seconds)">
              <input
                type="number"
                min={1}
                className="field"
                value={form.timeout_seconds ?? 60}
                onChange={(event) => setForm({ ...form, timeout_seconds: Number(event.target.value) })}
              />
            </Field>
            <Field label="Max retries">
              <input
                type="number"
                min={0}
                max={5}
                className="field"
                value={form.max_retries ?? 1}
                onChange={(event) => setForm({ ...form, max_retries: Number(event.target.value) })}
              />
            </Field>
            <Field label="RAG pipeline">
              <select
                className="field"
                value={form.rag_pipeline_id ?? ''}
                onChange={(event) => setForm({ ...form, rag_pipeline_id: event.target.value || null })}
              >
                <option value="">None</option>
                {pipelines.data?.map((pipeline) => (
                  <option key={pipeline.id} value={pipeline.id}>
                    {pipeline.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Guardrail policy">
              <select
                className="field"
                value={form.guardrail_policy_id ?? ''}
                onChange={(event) => setForm({ ...form, guardrail_policy_id: event.target.value || null })}
              >
                <option value="">Platform default</option>
                {policies.data?.map((policy) => (
                  <option key={policy.id} value={policy.id}>
                    {policy.name}
                  </option>
                ))}
              </select>
            </Field>
            <div className="sm:col-span-2">
              <Field label="System prompt">
                <textarea
                  className="field h-40 resize-y font-mono text-xs"
                  value={form.system_prompt ?? ''}
                  onChange={(event) => setForm({ ...form, system_prompt: event.target.value })}
                />
              </Field>
            </div>
          </fieldset>
        </Panel>

        <div className="space-y-4">
          <Panel title="Test this agent" description="Runs the full graph, including guardrails.">
            <textarea
              className="field h-24 resize-y text-sm"
              value={testInput}
              onChange={(event) => setTestInput(event.target.value)}
              aria-label="Test input"
            />
            <button
              type="button"
              className="btn-primary mt-2 w-full"
              disabled={run.isPending || !can('agents:execute')}
              onClick={() => run.mutate()}
            >
              {run.isPending ? 'Running…' : 'Run agent'}
            </button>

            {lastRun && (
              <div className="mt-3 space-y-2 rounded-md border border-border bg-canvas p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={toneForStatus(lastRun.status)}>{lastRun.status}</Badge>
                  <Badge tone={toneForStatus(lastRun.guardrail_outcome)}>{lastRun.guardrail_outcome}</Badge>
                  <span className="text-[11px] text-slate-500">
                    {formatNumber(lastRun.total_tokens)} tokens · {formatDuration(lastRun.latency_ms)}
                  </span>
                </div>
                <p className="whitespace-pre-wrap text-xs text-slate-300">{lastRun.output_text || '—'}</p>
                {lastRun.citations.length > 0 && (
                  <ul className="space-y-1 border-t border-border pt-2">
                    {lastRun.citations.map((citation, index) => (
                      <li key={citation.chunk_id} className="text-[11px] text-slate-400">
                        [{index + 1}] {citation.document_name}
                        {citation.page ? ` · p${citation.page}` : ''} · score {citation.score.toFixed(3)}
                      </li>
                    ))}
                  </ul>
                )}
                <Link className="btn-ghost w-full" to={`/runs/${lastRun.id}`}>
                  Open full trace
                </Link>
              </div>
            )}
          </Panel>

          <Panel title="Version history">
            {versions.isLoading ? (
              <LoadingPanel rows={3} />
            ) : (versions.data?.length ?? 0) === 0 ? (
              <EmptyState title="No versions recorded" />
            ) : (
              <ul className="space-y-2">
                {versions.data?.map((version) => (
                  <li
                    key={version.id}
                    className="flex items-start justify-between gap-2 rounded border border-border bg-canvas px-3 py-2"
                  >
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-slate-200">v{version.version}</p>
                      <p className="truncate text-[11px] text-slate-500">{version.changelog ?? '—'}</p>
                      <p className="text-[11px] text-slate-600">{formatDateTime(version.created_at)}</p>
                    </div>
                    {editable && version.version !== agent.data?.current_version && (
                      <button
                        type="button"
                        className="btn-ghost px-2 py-1 text-[11px]"
                        onClick={() => rollback.mutate(version.version)}
                      >
                        Roll back
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
      </div>

      <Panel className="mt-4" title="Execution history" description="The most recent runs for this agent">
        {runs.isLoading ? (
          <LoadingPanel rows={4} />
        ) : (
          <DataTable
            rows={runs.data?.items ?? []}
            keyOf={(item) => item.id}
            onRowClick={(item) => navigate(`/runs/${item.id}`)}
            emptyMessage="This agent has not been run yet."
            columns={[
              {
                key: 'status',
                header: 'Status',
                render: (item) => <Badge tone={toneForStatus(item.status)}>{item.status}</Badge>,
              },
              { key: 'model', header: 'Model', render: (item) => item.model_name ?? '—' },
              {
                key: 'tokens',
                header: 'Tokens',
                render: (item) => <span className="tabular-nums">{formatNumber(item.total_tokens)}</span>,
              },
              {
                key: 'latency',
                header: 'Latency',
                render: (item) => <span className="tabular-nums">{formatDuration(item.latency_ms)}</span>,
              },
              {
                key: 'guardrail',
                header: 'Guardrail',
                render: (item) => <Badge tone={toneForStatus(item.guardrail_outcome)}>{item.guardrail_outcome}</Badge>,
              },
              {
                key: 'created',
                header: 'When',
                render: (item) => <span className="text-xs text-slate-500">{formatRelative(item.created_at)}</span>,
              },
            ]}
          />
        )}
      </Panel>

      <ConfirmDialog
        open={confirmDelete}
        title="Archive agent"
        message="The agent will be disabled and hidden from the catalogue. Its run history is retained for audit."
        confirmLabel="Archive"
        busy={remove.isPending}
        onCancel={() => setConfirmDelete(false)}
        onConfirm={() => remove.mutate()}
      />
    </>
  )
}
