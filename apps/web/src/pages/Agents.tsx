import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import {
  Badge,
  DataTable,
  ErrorState,
  Field,
  LoadingPanel,
  Modal,
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
import type { Agent, AgentDetail, ModelEntry, Page, Pipeline } from '@/lib/types'
import { useAuthStore } from '@/store/auth'

interface DraftAgent {
  name: string
  description: string
  system_prompt: string
  model_id: string
  fallback_model_id: string
  rag_enabled: boolean
  environment: string
  tools: string[]
}

const EMPTY_DRAFT: DraftAgent = {
  name: '',
  description: '',
  system_prompt: 'Answer only from the retrieved context and cite your sources.',
  model_id: '',
  fallback_model_id: '',
  rag_enabled: true,
  environment: 'development',
  tools: [],
}

export function AgentsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { notify } = useToast()
  const can = useAuthStore((state) => state.can)
  const [environment, setEnvironment] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [creating, setCreating] = useState(false)
  const [draft, setDraft] = useState<DraftAgent>(EMPTY_DRAFT)

  const list = usePagedList<Agent>('agents', '/agents', {
    environment: environment || undefined,
    status_filter: statusFilter || undefined,
  })

  const models = useQuery({
    queryKey: ['models', 'chat'],
    queryFn: () => api.get<Page<ModelEntry>>('/models?kind=chat&page_size=100'),
  })
  const pipelines = useQuery({
    queryKey: ['pipelines'],
    queryFn: () => api.get<Pipeline[]>('/rag/pipelines'),
  })
  const topology = useQuery({
    queryKey: ['graph-topology'],
    queryFn: () => api.get<{ tools: { name: string; description: string }[] }>('/agents/graph-topology'),
  })

  const create = useMutation({
    mutationFn: () =>
      api.post<AgentDetail>('/agents', {
        name: draft.name,
        description: draft.description || null,
        system_prompt: draft.system_prompt,
        model_id: draft.model_id || null,
        fallback_model_id: draft.fallback_model_id || null,
        rag_enabled: draft.rag_enabled,
        rag_pipeline_id: draft.rag_enabled ? (pipelines.data?.find((p) => p.is_default)?.id ?? null) : null,
        environment: draft.environment,
        tools: draft.tools,
      }),
    onSuccess: (agent) => {
      notify(`Agent "${agent.name}" created.`, 'success')
      setCreating(false)
      setDraft(EMPTY_DRAFT)
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      navigate(`/agents/${agent.id}`)
    },
    onError: (error: Error) => notify(error.message, 'danger'),
  })

  return (
    <>
      <PageHeader
        title="AI Agent Manager"
        description="Register, configure, version and run the agents this organisation operates."
        actions={
          can('agents:write') && (
            <button type="button" className="btn-primary" onClick={() => setCreating(true)}>
              New agent
            </button>
          )
        }
      />

      <Panel
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <SearchInput value={list.state.search} onChange={list.state.setSearch} placeholder="Search agents…" />
            <select
              className="field w-auto"
              aria-label="Filter by environment"
              value={environment}
              onChange={(event) => setEnvironment(event.target.value)}
            >
              <option value="">All environments</option>
              <option value="development">Development</option>
              <option value="staging">Staging</option>
              <option value="production">Production</option>
            </select>
            <select
              className="field w-auto"
              aria-label="Filter by status"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option value="">All statuses</option>
              <option value="active">Active</option>
              <option value="draft">Draft</option>
              <option value="paused">Paused</option>
              <option value="archived">Archived</option>
            </select>
          </div>
        }
      >
        {list.isLoading ? (
          <LoadingPanel rows={6} />
        ) : list.error ? (
          <ErrorState error={list.error} onRetry={() => list.refetch()} />
        ) : (
          <>
            <DataTable
              rows={list.data?.items ?? []}
              keyOf={(agent) => agent.id}
              onRowClick={(agent) => navigate(`/agents/${agent.id}`)}
              sortBy={list.state.sortBy}
              sortDir={list.state.sortDir}
              onSort={list.state.toggleSort}
              emptyMessage="No agents match these filters."
              columns={[
                {
                  key: 'name',
                  header: 'Agent',
                  sortable: true,
                  render: (agent) => (
                    <div className="flex items-start gap-2">
                      <StatusDot status={agent.status} />
                      <div className="min-w-0">
                        <p className="truncate font-medium text-slate-100">{agent.name}</p>
                        <p className="truncate text-xs text-slate-500">{agent.description ?? agent.slug}</p>
                      </div>
                    </div>
                  ),
                },
                {
                  key: 'status',
                  header: 'Status',
                  sortable: true,
                  render: (agent) => (
                    <div className="flex flex-wrap gap-1">
                      <Badge tone={toneForStatus(agent.status)}>{agent.status}</Badge>
                      {!agent.enabled && <Badge tone="neutral">disabled</Badge>}
                    </div>
                  ),
                },
                {
                  key: 'environment',
                  header: 'Environment',
                  sortable: true,
                  render: (agent) => <span className="text-slate-300">{agent.environment}</span>,
                },
                {
                  key: 'capabilities',
                  header: 'Capabilities',
                  render: (agent) => (
                    <div className="flex flex-wrap gap-1">
                      {agent.rag_enabled && <Badge tone="accent">RAG</Badge>}
                      {agent.tools.map((tool) => (
                        <Badge key={tool} tone="info">
                          {tool}
                        </Badge>
                      ))}
                      {!agent.rag_enabled && agent.tools.length === 0 && (
                        <span className="text-xs text-slate-500">—</span>
                      )}
                    </div>
                  ),
                },
                {
                  key: 'current_version',
                  header: 'Version',
                  sortable: true,
                  render: (agent) => <span className="tabular-nums text-slate-300">v{agent.current_version}</span>,
                },
                {
                  key: 'updated_at',
                  header: 'Updated',
                  sortable: true,
                  render: (agent) => <span className="text-xs text-slate-500">{formatRelative(agent.updated_at)}</span>,
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

      <Modal
        open={creating}
        title="Create agent"
        onClose={() => setCreating(false)}
        wide
        footer={
          <>
            <button type="button" className="btn-ghost" onClick={() => setCreating(false)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={!draft.name.trim() || create.isPending}
              onClick={() => create.mutate()}
            >
              {create.isPending ? 'Creating…' : 'Create agent'}
            </button>
          </>
        }
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name">
            <input
              className="field"
              value={draft.name}
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              placeholder="Support Answering Agent"
            />
          </Field>
          <Field label="Environment">
            <select
              className="field"
              value={draft.environment}
              onChange={(event) => setDraft({ ...draft, environment: event.target.value })}
            >
              <option value="development">Development</option>
              <option value="staging">Staging</option>
              <option value="production">Production</option>
            </select>
          </Field>
          <Field label="Description" hint="Shown in the agent list">
            <input
              className="field"
              value={draft.description}
              onChange={(event) => setDraft({ ...draft, description: event.target.value })}
            />
          </Field>
          <Field label="Model">
            <select
              className="field"
              value={draft.model_id}
              onChange={(event) => setDraft({ ...draft, model_id: event.target.value })}
            >
              <option value="">Platform default</option>
              {models.data?.items.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Fallback model" hint="Used when the primary deployment fails">
            <select
              className="field"
              value={draft.fallback_model_id}
              onChange={(event) => setDraft({ ...draft, fallback_model_id: event.target.value })}
            >
              <option value="">None</option>
              {models.data?.items.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Retrieval">
            <label className="flex items-center gap-2 pt-2 text-sm text-slate-300">
              <input
                type="checkbox"
                checked={draft.rag_enabled}
                onChange={(event) => setDraft({ ...draft, rag_enabled: event.target.checked })}
              />
              Answer from indexed documents
            </label>
          </Field>
          <div className="sm:col-span-2">
            <Field label="System prompt">
              <textarea
                className="field h-28 resize-y font-mono text-xs"
                value={draft.system_prompt}
                onChange={(event) => setDraft({ ...draft, system_prompt: event.target.value })}
              />
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Field label="Tools" hint="Only allowlisted tools can execute at run time">
              <div className="flex flex-wrap gap-3 pt-1">
                {(topology.data?.tools ?? []).map((tool) => (
                  <label key={tool.name} className="flex items-center gap-2 text-sm text-slate-300" title={tool.description}>
                    <input
                      type="checkbox"
                      checked={draft.tools.includes(tool.name)}
                      onChange={(event) =>
                        setDraft({
                          ...draft,
                          tools: event.target.checked
                            ? [...draft.tools, tool.name]
                            : draft.tools.filter((name) => name !== tool.name),
                        })
                      }
                    />
                    {tool.name}
                  </label>
                ))}
              </div>
            </Field>
          </div>
        </div>
      </Modal>
    </>
  )
}
