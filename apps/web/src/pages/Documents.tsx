import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'

import {
  Badge,
  ConfirmDialog,
  DataTable,
  EmptyState,
  ErrorState,
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
import { formatBytes, formatNumber, formatRelative } from '@/lib/format'
import { usePagedList } from '@/lib/hooks'
import type { Chunk, DocumentDetail, DocumentSummary, Page } from '@/lib/types'
import { useAuthStore } from '@/store/auth'

export function DocumentsPage() {
  const queryClient = useQueryClient()
  const { notify } = useToast()
  const can = useAuthStore((state) => state.can)
  const fileInput = useRef<HTMLInputElement>(null)

  const [statusFilter, setStatusFilter] = useState('')
  const [dragging, setDragging] = useState(false)
  const [selected, setSelected] = useState<DocumentSummary | null>(null)
  const [pendingDelete, setPendingDelete] = useState<DocumentSummary | null>(null)

  const list = usePagedList<DocumentSummary>('documents', '/documents', {
    status_filter: statusFilter || undefined,
  })

  const detail = useQuery({
    queryKey: ['document', selected?.id],
    queryFn: () => api.get<DocumentDetail>(`/documents/${selected?.id}`),
    enabled: Boolean(selected),
  })

  const chunks = useQuery({
    queryKey: ['chunks', selected?.id],
    queryFn: () => api.get<Page<Chunk>>(`/documents/${selected?.id}/chunks?page_size=20`),
    enabled: Boolean(selected),
  })

  const upload = useMutation({
    mutationFn: async (files: FileList) => {
      const results = []
      for (const file of Array.from(files)) {
        const form = new FormData()
        form.append('file', file)
        results.push(await api.upload<DocumentDetail>('/documents', form))
      }
      return results
    },
    onSuccess: (documents) => {
      const indexed = documents.filter((doc) => doc.status === 'indexed').length
      notify(`${indexed}/${documents.length} document(s) indexed.`, indexed ? 'success' : 'warning')
      queryClient.invalidateQueries({ queryKey: ['documents'] })
    },
    onError: (error: Error) => notify(error.message, 'danger'),
  })

  const reprocess = useMutation({
    mutationFn: (id: string) => api.post<DocumentDetail>(`/documents/${id}/reprocess`),
    onSuccess: (document) => {
      notify(`Reprocessed: ${document.status}.`, document.status === 'indexed' ? 'success' : 'warning')
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      queryClient.invalidateQueries({ queryKey: ['document', document.id] })
    },
    onError: (error: Error) => notify(error.message, 'danger'),
  })

  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`/documents/${id}`),
    onSuccess: () => {
      notify('Document deleted and de-indexed.', 'info')
      setPendingDelete(null)
      setSelected(null)
      queryClient.invalidateQueries({ queryKey: ['documents'] })
    },
    onError: (error: Error) => notify(error.message, 'danger'),
  })

  return (
    <>
      <PageHeader
        title="Document Intelligence"
        description="Upload, extract, chunk, embed and index the corpus your agents answer from."
        actions={
          can('documents:write') && (
            <button type="button" className="btn-primary" onClick={() => fileInput.current?.click()}>
              Upload documents
            </button>
          )
        }
      />

      <input
        ref={fileInput}
        type="file"
        multiple
        className="hidden"
        accept=".pdf,.txt,.md,.csv,.json,.docx"
        onChange={(event) => {
          if (event.target.files?.length) upload.mutate(event.target.files)
          event.target.value = ''
        }}
      />

      {can('documents:write') && (
        <div
          onDragOver={(event) => {
            event.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault()
            setDragging(false)
            if (event.dataTransfer.files?.length) upload.mutate(event.dataTransfer.files)
          }}
          className={`mb-4 rounded-lg border-2 border-dashed px-4 py-6 text-center text-sm transition-colors ${
            dragging ? 'border-azure-400 bg-azure-500/10 text-azure-100' : 'border-border text-slate-500'
          }`}
        >
          {upload.isPending ? (
            <span>Uploading and indexing…</span>
          ) : (
            <span>
              Drop PDF, DOCX, TXT, MD, CSV or JSON files here — each one is extracted, chunked, embedded and indexed
              immediately.
            </span>
          )}
        </div>
      )}

      <Panel
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <SearchInput value={list.state.search} onChange={list.state.setSearch} placeholder="Search documents…" />
            <select
              className="field w-auto"
              aria-label="Filter by status"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option value="">All statuses</option>
              <option value="indexed">Indexed</option>
              <option value="pending">Pending</option>
              <option value="failed">Failed</option>
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
              keyOf={(document) => document.id}
              onRowClick={setSelected}
              sortBy={list.state.sortBy}
              sortDir={list.state.sortDir}
              onSort={list.state.toggleSort}
              emptyMessage="No documents indexed yet."
              columns={[
                {
                  key: 'filename',
                  header: 'Document',
                  sortable: true,
                  render: (document) => (
                    <div className="flex items-start gap-2">
                      <StatusDot status={document.status} />
                      <div className="min-w-0">
                        <p className="truncate font-medium text-slate-100">{document.filename}</p>
                        <p className="text-xs text-slate-500">
                          {formatBytes(document.size_bytes)} · v{document.version}
                        </p>
                      </div>
                    </div>
                  ),
                },
                {
                  key: 'status',
                  header: 'Status',
                  sortable: true,
                  render: (document) => (
                    <div>
                      <Badge tone={toneForStatus(document.status)}>{document.status}</Badge>
                      {document.error_message && (
                        <p className="mt-1 max-w-xs truncate text-[11px] text-red-300" title={document.error_message}>
                          {document.error_message}
                        </p>
                      )}
                    </div>
                  ),
                },
                {
                  key: 'chunk_count',
                  header: 'Chunks',
                  sortable: true,
                  render: (document) => <span className="tabular-nums">{formatNumber(document.chunk_count)}</span>,
                },
                {
                  key: 'tags',
                  header: 'Tags',
                  render: (document) => (
                    <div className="flex flex-wrap gap-1">
                      {document.tags.slice(0, 3).map((tag) => (
                        <Badge key={tag} tone="neutral">
                          {tag}
                        </Badge>
                      ))}
                    </div>
                  ),
                },
                {
                  key: 'created_at',
                  header: 'Uploaded',
                  sortable: true,
                  render: (document) => (
                    <span className="text-xs text-slate-500">{formatRelative(document.created_at)}</span>
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

      <Modal
        open={Boolean(selected)}
        title={selected?.filename ?? 'Document'}
        onClose={() => setSelected(null)}
        wide
        footer={
          <>
            {can('documents:write') && selected && (
              <button
                type="button"
                className="btn-ghost"
                disabled={reprocess.isPending}
                onClick={() => reprocess.mutate(selected.id)}
              >
                {reprocess.isPending ? 'Reprocessing…' : 'Reprocess'}
              </button>
            )}
            {can('documents:delete') && selected && (
              <button type="button" className="btn-danger" onClick={() => setPendingDelete(selected)}>
                Delete
              </button>
            )}
            <button type="button" className="btn-ghost" onClick={() => setSelected(null)}>
              Close
            </button>
          </>
        }
      >
        {detail.isLoading ? (
          <LoadingPanel rows={6} />
        ) : detail.data ? (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <Badge tone={toneForStatus(detail.data.status)}>{detail.data.status}</Badge>
              <Badge tone="neutral">{detail.data.content_type}</Badge>
              <Badge tone="neutral">{formatBytes(detail.data.size_bytes)}</Badge>
              <Badge tone="info">{detail.data.chunk_count} chunks</Badge>
              {detail.data.page_count > 1 && <Badge tone="neutral">{detail.data.page_count} pages</Badge>}
              {detail.data.is_demo && <Badge tone="accent">demo data</Badge>}
            </div>

            {Array.isArray((detail.data.doc_metadata as { warnings?: string[] })?.warnings) && (
              <ul className="rounded border border-warn/40 bg-warn/10 px-3 py-2 text-xs text-amber-200">
                {((detail.data.doc_metadata as { warnings: string[] }).warnings ?? []).map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            )}

            <section>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Extracted text</h3>
              <pre className="max-h-52 overflow-auto whitespace-pre-wrap rounded bg-canvas p-3 text-[11px] text-slate-400">
                {detail.data.extracted_text_preview ?? 'No text extracted.'}
              </pre>
            </section>

            <section>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Chunks</h3>
              {chunks.isLoading ? (
                <LoadingPanel rows={3} />
              ) : (chunks.data?.items.length ?? 0) === 0 ? (
                <EmptyState title="No chunks" description="This document produced no indexable chunks." />
              ) : (
                <ol className="space-y-2">
                  {chunks.data?.items.map((chunk) => (
                    <li key={chunk.id} className="rounded border border-border bg-canvas px-3 py-2">
                      <div className="flex items-center justify-between text-[11px] text-slate-500">
                        <span>
                          chunk {chunk.ordinal}
                          {chunk.page ? ` · page ${chunk.page}` : ''}
                        </span>
                        <span>
                          ~{chunk.token_estimate} tokens · {chunk.embedding_model ?? 'not embedded'}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-slate-400">{chunk.content}</p>
                    </li>
                  ))}
                </ol>
              )}
            </section>
          </div>
        ) : null}
      </Modal>

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Delete document"
        message={`"${pendingDelete?.filename}" will be removed from the vector index and hidden from retrieval. Audit history is retained.`}
        confirmLabel="Delete"
        busy={remove.isPending}
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => pendingDelete && remove.mutate(pendingDelete.id)}
      />
    </>
  )
}
