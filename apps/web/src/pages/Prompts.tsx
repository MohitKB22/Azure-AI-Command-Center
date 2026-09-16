import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

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
  SearchInput,
  toneForStatus,
  useToast,
} from '@/components/ui'
import { api } from '@/lib/api'
import { formatDateTime, formatRelative } from '@/lib/format'
import { usePagedList } from '@/lib/hooks'
import type { Prompt } from '@/lib/types'
import { useAuthStore } from '@/store/auth'

export function PromptsPage() {
  const queryClient = useQueryClient()
  const { notify } = useToast()
  const can = useAuthStore((state) => state.can)

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [draft, setDraft] = useState({ key: '', name: '', description: '', template: '' })
  const [newTemplate, setNewTemplate] = useState('')
  const [variables, setVariables] = useState<Record<string, string>>({})
  const [rendered, setRendered] = useState<{ rendered: string; missing_variables: string[] } | null>(null)
  const [compareWith, setCompareWith] = useState<number | null>(null)

  const list = usePagedList<Prompt>('prompts', '/prompts')

  const detail = useQuery({
    queryKey: ['prompt', selectedId],
    queryFn: () => api.get<Prompt>(`/prompts/${selectedId}`),
    enabled: Boolean(selectedId),
  })

  const activeVersion = detail.data?.versions?.find((v) => v.version === detail.data?.active_version)
  const comparison = detail.data?.versions?.find((v) => v.version === compareWith)

  const create = useMutation({
    mutationFn: () => api.post<Prompt>('/prompts', draft),
    onSuccess: (prompt) => {
      notify('Prompt registered.', 'success')
      setCreating(false)
      setDraft({ key: '', name: '', description: '', template: '' })
      queryClient.invalidateQueries({ queryKey: ['prompts'] })
      setSelectedId(prompt.id)
    },
    onError: (error: Error) => notify(error.message, 'danger'),
  })

  const addVersion = useMutation({
    mutationFn: () => api.post(`/prompts/${selectedId}/versions`, { template: newTemplate, changelog: 'Edited in UI' }),
    onSuccess: () => {
      notify('New version saved and activated.', 'success')
      setNewTemplate('')
      queryClient.invalidateQueries({ queryKey: ['prompt', selectedId] })
      queryClient.invalidateQueries({ queryKey: ['prompts'] })
    },
    onError: (error: Error) => notify(error.message, 'danger'),
  })

  const rollback = useMutation({
    mutationFn: (version: number) => api.post(`/prompts/${selectedId}/rollback/${version}`),
    onSuccess: () => {
      notify('Active version changed.', 'success')
      queryClient.invalidateQueries({ queryKey: ['prompt', selectedId] })
    },
    onError: (error: Error) => notify(error.message, 'danger'),
  })

  const render = useMutation({
    mutationFn: () =>
      api.post<{ rendered: string; missing_variables: string[]; version: number }>(
        `/prompts/${selectedId}/render`,
        { variables },
      ),
    onSuccess: setRendered,
    onError: (error: Error) => notify(error.message, 'danger'),
  })

  return (
    <>
      <PageHeader
        title="Prompt Management"
        description="Versioned prompt registry with variables, environment promotion, rollback and a test playground."
        actions={
          can('prompts:write') && (
            <button type="button" className="btn-primary" onClick={() => setCreating(true)}>
              New prompt
            </button>
          )
        }
      />

      <Panel actions={<SearchInput value={list.state.search} onChange={list.state.setSearch} placeholder="Search prompts…" />}>
        {list.isLoading ? (
          <LoadingPanel rows={5} />
        ) : list.error ? (
          <ErrorState error={list.error} onRetry={() => list.refetch()} />
        ) : (
          <>
            <DataTable
              rows={list.data?.items ?? []}
              keyOf={(prompt) => prompt.id}
              onRowClick={(prompt) => {
                setSelectedId(prompt.id)
                setRendered(null)
                setCompareWith(null)
              }}
              sortBy={list.state.sortBy}
              sortDir={list.state.sortDir}
              onSort={list.state.toggleSort}
              columns={[
                {
                  key: 'name',
                  header: 'Prompt',
                  sortable: true,
                  render: (prompt) => (
                    <div>
                      <p className="font-medium text-slate-100">{prompt.name}</p>
                      <p className="font-mono text-[11px] text-slate-500">{prompt.key}</p>
                    </div>
                  ),
                },
                {
                  key: 'active_version',
                  header: 'Active version',
                  render: (prompt) => <Badge tone="info">v{prompt.active_version}</Badge>,
                },
                {
                  key: 'tags',
                  header: 'Tags',
                  render: (prompt) => (
                    <div className="flex flex-wrap gap-1">
                      {prompt.tags.map((tag) => (
                        <Badge key={tag} tone="neutral">
                          {tag}
                        </Badge>
                      ))}
                    </div>
                  ),
                },
                {
                  key: 'updated_at',
                  header: 'Updated',
                  sortable: true,
                  render: (prompt) => <span className="text-xs text-slate-500">{formatRelative(prompt.updated_at)}</span>,
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

      <Modal open={Boolean(selectedId)} title={detail.data?.name ?? 'Prompt'} onClose={() => setSelectedId(null)} wide>
        {detail.isLoading ? (
          <LoadingPanel rows={6} />
        ) : detail.data ? (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <Badge tone="info">active v{detail.data.active_version}</Badge>
              {activeVersion && <Badge tone={toneForStatus(activeVersion.approval_status)}>{activeVersion.approval_status}</Badge>}
              {activeVersion && <Badge tone="neutral">{activeVersion.environment}</Badge>}
            </div>

            <section>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Active template</h3>
              <pre className="whitespace-pre-wrap rounded bg-canvas p-3 text-xs text-slate-300">
                {activeVersion?.template ?? '—'}
              </pre>
              {activeVersion && activeVersion.variables.length > 0 && (
                <p className="mt-1 text-[11px] text-slate-500">Variables: {activeVersion.variables.join(', ')}</p>
              )}
            </section>

            <section>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Test playground</h3>
              <div className="grid gap-2 sm:grid-cols-2">
                {(activeVersion?.variables ?? []).map((variable) => (
                  <Field key={variable} label={variable}>
                    <input
                      className="field"
                      value={variables[variable] ?? ''}
                      onChange={(event) => setVariables({ ...variables, [variable]: event.target.value })}
                    />
                  </Field>
                ))}
              </div>
              <button type="button" className="btn-ghost mt-2" onClick={() => render.mutate()}>
                Render
              </button>
              {rendered && (
                <div className="mt-2">
                  <pre className="whitespace-pre-wrap rounded border border-azure-500/30 bg-azure-500/5 p-3 text-xs text-slate-200">
                    {rendered.rendered}
                  </pre>
                  {rendered.missing_variables.length > 0 && (
                    <p className="mt-1 text-[11px] text-amber-300">
                      Missing variables: {rendered.missing_variables.join(', ')}
                    </p>
                  )}
                </div>
              )}
            </section>

            <section>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Versions</h3>
              {(detail.data.versions?.length ?? 0) === 0 ? (
                <EmptyState title="No versions" />
              ) : (
                <ul className="space-y-2">
                  {detail.data.versions?.map((version) => (
                    <li key={version.id} className="rounded border border-border bg-canvas px-3 py-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="flex items-center gap-2 text-xs text-slate-200">
                          v{version.version}
                          <Badge tone={toneForStatus(version.approval_status)}>{version.approval_status}</Badge>
                          <Badge tone="neutral">{version.environment}</Badge>
                          {version.version === detail.data?.active_version && <Badge tone="success">active</Badge>}
                        </span>
                        <span className="flex items-center gap-2">
                          <button
                            type="button"
                            className="btn-ghost px-2 py-1 text-[11px]"
                            onClick={() => setCompareWith(compareWith === version.version ? null : version.version)}
                          >
                            {compareWith === version.version ? 'Hide' : 'Compare'}
                          </button>
                          {can('prompts:write') && version.version !== detail.data?.active_version && (
                            <button
                              type="button"
                              className="btn-ghost px-2 py-1 text-[11px]"
                              onClick={() => rollback.mutate(version.version)}
                            >
                              Activate
                            </button>
                          )}
                        </span>
                      </div>
                      <p className="mt-1 text-[11px] text-slate-500">
                        {version.changelog ?? '—'} · {formatDateTime(version.created_at)}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {comparison && activeVersion && (
              <section className="grid gap-2 sm:grid-cols-2">
                <div>
                  <p className="mb-1 text-[11px] text-slate-500">Active v{activeVersion.version}</p>
                  <pre className="max-h-52 overflow-auto whitespace-pre-wrap rounded bg-canvas p-3 text-[11px] text-slate-300">
                    {activeVersion.template}
                  </pre>
                </div>
                <div>
                  <p className="mb-1 text-[11px] text-slate-500">v{comparison.version}</p>
                  <pre className="max-h-52 overflow-auto whitespace-pre-wrap rounded bg-canvas p-3 text-[11px] text-slate-300">
                    {comparison.template}
                  </pre>
                </div>
              </section>
            )}

            {can('prompts:write') && (
              <section>
                <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">New version</h3>
                <textarea
                  className="field h-28 resize-y font-mono text-xs"
                  placeholder="Use {{variable}} placeholders"
                  value={newTemplate}
                  onChange={(event) => setNewTemplate(event.target.value)}
                />
                <button
                  type="button"
                  className="btn-primary mt-2"
                  disabled={!newTemplate.trim() || addVersion.isPending}
                  onClick={() => addVersion.mutate()}
                >
                  {addVersion.isPending ? 'Saving…' : 'Save as new version'}
                </button>
              </section>
            )}
          </div>
        ) : null}
      </Modal>

      <Modal
        open={creating}
        title="Register prompt"
        onClose={() => setCreating(false)}
        footer={
          <>
            <button type="button" className="btn-ghost" onClick={() => setCreating(false)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={!draft.key || !draft.name || !draft.template || create.isPending}
              onClick={() => create.mutate()}
            >
              {create.isPending ? 'Creating…' : 'Create'}
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <Field label="Key" hint="Lowercase identifier, e.g. support.answer">
            <input className="field" value={draft.key} onChange={(e) => setDraft({ ...draft, key: e.target.value })} />
          </Field>
          <Field label="Name">
            <input className="field" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
          </Field>
          <Field label="Description">
            <input
              className="field"
              value={draft.description}
              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
            />
          </Field>
          <Field label="Template" hint="Use {{variable}} placeholders">
            <textarea
              className="field h-32 resize-y font-mono text-xs"
              value={draft.template}
              onChange={(e) => setDraft({ ...draft, template: e.target.value })}
            />
          </Field>
        </div>
      </Modal>
    </>
  )
}
