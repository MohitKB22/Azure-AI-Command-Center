import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

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
  toneForStatus,
  useToast,
} from '@/components/ui'
import { api } from '@/lib/api'
import { formatNumber } from '@/lib/format'
import { usePagedList } from '@/lib/hooks'
import type { ModelEntry } from '@/lib/types'
import { useAuthStore } from '@/store/auth'

const EMPTY = {
  name: '',
  provider: 'azure_openai',
  deployment_name: '',
  kind: 'chat',
  context_window: 128000,
  max_output_tokens: 4096,
  input_cost_per_1k: 0,
  output_cost_per_1k: 0,
}

export function ModelsPage() {
  const queryClient = useQueryClient()
  const { notify } = useToast()
  const can = useAuthStore((state) => state.can)
  const [kind, setKind] = useState('')
  const [creating, setCreating] = useState(false)
  const [draft, setDraft] = useState({ ...EMPTY })
  const [editing, setEditing] = useState<ModelEntry | null>(null)

  const list = usePagedList<ModelEntry>('models-page', '/models', { kind: kind || undefined }, 25)

  const create = useMutation({
    mutationFn: () => api.post<ModelEntry>('/models', draft),
    onSuccess: () => {
      notify('Model added to the catalogue.', 'success')
      setCreating(false)
      setDraft({ ...EMPTY })
      queryClient.invalidateQueries({ queryKey: ['models-page'] })
    },
    onError: (error: Error) => notify(error.message, 'danger'),
  })

  const update = useMutation({
    mutationFn: (patch: Partial<ModelEntry>) => api.patch<ModelEntry>(`/models/${editing?.id}`, patch),
    onSuccess: () => {
      notify('Model updated. New pricing applies to future usage only.', 'success')
      setEditing(null)
      queryClient.invalidateQueries({ queryKey: ['models-page'] })
    },
    onError: (error: Error) => notify(error.message, 'danger'),
  })

  return (
    <>
      <PageHeader
        title="Model Center"
        description="The models agents are permitted to call, with the cost configuration used for all billing maths."
        actions={
          can('models:write') && (
            <button type="button" className="btn-primary" onClick={() => setCreating(true)}>
              Add model
            </button>
          )
        }
      />

      <Panel
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <SearchInput value={list.state.search} onChange={list.state.setSearch} placeholder="Search models…" />
            <select className="field w-auto" aria-label="Filter by kind" value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">All kinds</option>
              <option value="chat">Chat</option>
              <option value="embedding">Embedding</option>
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
              keyOf={(model) => model.id}
              onRowClick={can('models:write') ? setEditing : undefined}
              sortBy={list.state.sortBy}
              sortDir={list.state.sortDir}
              onSort={list.state.toggleSort}
              columns={[
                {
                  key: 'name',
                  header: 'Model',
                  sortable: true,
                  render: (model) => (
                    <div>
                      <p className="font-medium text-slate-100">{model.name}</p>
                      <p className="font-mono text-[11px] text-slate-500">
                        {model.provider} / {model.deployment_name}
                      </p>
                    </div>
                  ),
                },
                {
                  key: 'kind',
                  header: 'Kind',
                  render: (model) => <Badge tone={model.kind === 'chat' ? 'info' : 'accent'}>{model.kind}</Badge>,
                },
                {
                  key: 'context_window',
                  header: 'Context',
                  sortable: true,
                  render: (model) => <span className="tabular-nums">{formatNumber(model.context_window)}</span>,
                },
                {
                  key: 'cost',
                  header: 'Cost / 1K tokens',
                  render: (model) => (
                    <span className="font-mono text-xs tabular-nums text-slate-300">
                      in ${model.input_cost_per_1k} · out ${model.output_cost_per_1k}
                    </span>
                  ),
                },
                {
                  key: 'capabilities',
                  header: 'Capabilities',
                  render: (model) => (
                    <div className="flex flex-wrap gap-1">
                      {model.capabilities.slice(0, 3).map((capability) => (
                        <Badge key={capability} tone="neutral">
                          {capability}
                        </Badge>
                      ))}
                    </div>
                  ),
                },
                {
                  key: 'status',
                  header: 'Status',
                  sortable: true,
                  render: (model) => (
                    <div className="flex flex-wrap gap-1">
                      <Badge tone={toneForStatus(model.status)}>{model.status}</Badge>
                      {model.is_default && <Badge tone="success">default</Badge>}
                      {model.is_fallback && <Badge tone="warning">fallback</Badge>}
                    </div>
                  ),
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

      <Panel className="mt-4" title="Routing">
        <p className="text-sm text-slate-400">
          Agents pick a primary model and an optional fallback. If the primary deployment fails after its retry budget,
          the run switches to the fallback and the run record is flagged{' '}
          <Badge tone="warning">fallback</Badge>. Cost is always calculated from the model that actually served the
          request, using the rates configured here.
        </p>
      </Panel>

      <Modal
        open={creating}
        title="Add model to catalogue"
        onClose={() => setCreating(false)}
        footer={
          <>
            <button type="button" className="btn-ghost" onClick={() => setCreating(false)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={!draft.name || !draft.deployment_name || create.isPending}
              onClick={() => create.mutate()}
            >
              {create.isPending ? 'Adding…' : 'Add model'}
            </button>
          </>
        }
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Display name">
            <input className="field" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
          </Field>
          <Field label="Deployment name">
            <input
              className="field"
              value={draft.deployment_name}
              onChange={(e) => setDraft({ ...draft, deployment_name: e.target.value })}
            />
          </Field>
          <Field label="Provider">
            <input
              className="field"
              value={draft.provider}
              onChange={(e) => setDraft({ ...draft, provider: e.target.value })}
            />
          </Field>
          <Field label="Kind">
            <select className="field" value={draft.kind} onChange={(e) => setDraft({ ...draft, kind: e.target.value })}>
              <option value="chat">chat</option>
              <option value="embedding">embedding</option>
            </select>
          </Field>
          <Field label="Context window">
            <input
              type="number"
              className="field"
              value={draft.context_window}
              onChange={(e) => setDraft({ ...draft, context_window: Number(e.target.value) })}
            />
          </Field>
          <Field label="Max output tokens">
            <input
              type="number"
              className="field"
              value={draft.max_output_tokens}
              onChange={(e) => setDraft({ ...draft, max_output_tokens: Number(e.target.value) })}
            />
          </Field>
          <Field label="Input cost per 1K">
            <input
              type="number"
              step="0.00001"
              className="field"
              value={draft.input_cost_per_1k}
              onChange={(e) => setDraft({ ...draft, input_cost_per_1k: Number(e.target.value) })}
            />
          </Field>
          <Field label="Output cost per 1K">
            <input
              type="number"
              step="0.00001"
              className="field"
              value={draft.output_cost_per_1k}
              onChange={(e) => setDraft({ ...draft, output_cost_per_1k: Number(e.target.value) })}
            />
          </Field>
        </div>
      </Modal>

      <Modal
        open={Boolean(editing)}
        title={editing?.name ?? 'Model'}
        onClose={() => setEditing(null)}
        footer={
          <>
            <button type="button" className="btn-ghost" onClick={() => setEditing(null)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={update.isPending}
              onClick={() =>
                editing &&
                update.mutate({
                  input_cost_per_1k: editing.input_cost_per_1k,
                  output_cost_per_1k: editing.output_cost_per_1k,
                  status: editing.status,
                  is_default: editing.is_default,
                  is_fallback: editing.is_fallback,
                })
              }
            >
              {update.isPending ? 'Saving…' : 'Save'}
            </button>
          </>
        }
      >
        {editing && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Input cost per 1K">
              <input
                type="number"
                step="0.00001"
                className="field"
                value={editing.input_cost_per_1k}
                onChange={(e) => setEditing({ ...editing, input_cost_per_1k: Number(e.target.value) })}
              />
            </Field>
            <Field label="Output cost per 1K">
              <input
                type="number"
                step="0.00001"
                className="field"
                value={editing.output_cost_per_1k}
                onChange={(e) => setEditing({ ...editing, output_cost_per_1k: Number(e.target.value) })}
              />
            </Field>
            <Field label="Status">
              <select
                className="field"
                value={editing.status}
                onChange={(e) => setEditing({ ...editing, status: e.target.value })}
              >
                <option value="available">available</option>
                <option value="deprecated">deprecated</option>
                <option value="retired">retired</option>
              </select>
            </Field>
            <div className="flex flex-col justify-end gap-2 pb-1">
              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input
                  type="checkbox"
                  checked={editing.is_default}
                  onChange={(e) => setEditing({ ...editing, is_default: e.target.checked })}
                />
                Platform default
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input
                  type="checkbox"
                  checked={editing.is_fallback}
                  onChange={(e) => setEditing({ ...editing, is_fallback: e.target.checked })}
                />
                Platform fallback
              </label>
            </div>
          </div>
        )}
      </Modal>
    </>
  )
}
