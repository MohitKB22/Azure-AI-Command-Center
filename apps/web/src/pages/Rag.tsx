import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { useState } from 'react'

import {
  Badge,
  EmptyState,
  ErrorState,
  Field,
  LoadingPanel,
  PageHeader,
  Panel,
  useToast,
} from '@/components/ui'
import { api } from '@/lib/api'
import { formatDuration } from '@/lib/format'
import type { Pipeline, RagQueryResponse } from '@/lib/types'
import { useAuthStore } from '@/store/auth'

interface Stage {
  id: string
  label: string
  description: string
}

export function RagPage() {
  const queryClient = useQueryClient()
  const { notify } = useToast()
  const can = useAuthStore((state) => state.can)

  const [query, setQuery] = useState('What is the default chunk size and overlap?')
  const [pipelineId, setPipelineId] = useState('')
  const [topK, setTopK] = useState(5)
  const [threshold, setThreshold] = useState(0.05)
  const [rerank, setRerank] = useState(true)
  const [generate, setGenerate] = useState(true)
  const [result, setResult] = useState<RagQueryResponse | null>(null)

  const stages = useQuery({ queryKey: ['rag-stages'], queryFn: () => api.get<Stage[]>('/rag/stages') })
  const pipelines = useQuery({ queryKey: ['pipelines'], queryFn: () => api.get<Pipeline[]>('/rag/pipelines') })

  const activePipeline = pipelines.data?.find((p) => (pipelineId ? p.id === pipelineId : p.is_default))

  const search = useMutation({
    mutationFn: () =>
      api.post<RagQueryResponse>('/rag/query', {
        query,
        pipeline_id: pipelineId || null,
        top_k: topK,
        similarity_threshold: threshold,
        use_reranking: rerank,
        generate_answer: generate,
      }),
    onSuccess: setResult,
    onError: (error: Error) => notify(error.message, 'danger'),
  })

  const savePipeline = useMutation({
    mutationFn: (patch: Partial<Pipeline>) => api.patch<Pipeline>(`/rag/pipelines/${activePipeline?.id}`, patch),
    onSuccess: () => {
      notify('Pipeline updated.', 'success')
      queryClient.invalidateQueries({ queryKey: ['pipelines'] })
    },
    onError: (error: Error) => notify(error.message, 'danger'),
  })

  const executedStages = new Set(result?.stages.map((stage) => stage.stage) ?? [])

  return (
    <>
      <PageHeader
        title="RAG Pipeline"
        description="Configure retrieval, then test it against the indexed corpus and inspect every stage."
      />

      <Panel title="Pipeline" description="Document to answer, stage by stage">
        {stages.isLoading ? (
          <LoadingPanel rows={2} />
        ) : (
          <ol className="flex flex-wrap items-stretch gap-2">
            {stages.data?.map((stage, index) => {
              const executed =
                executedStages.has(stage.id) ||
                (stage.id === 'vector_search' && executedStages.has('vector_search')) ||
                (result !== null &&
                  ['document', 'extraction', 'cleaning', 'chunking', 'embedding', 'index', 'retrieval'].includes(
                    stage.id,
                  ))
              return (
                <li key={stage.id} className="flex items-center gap-2">
                  <div
                    className={clsx(
                      'min-w-[128px] rounded-md border px-3 py-2',
                      executed ? 'border-azure-500/40 bg-azure-500/10' : 'border-border bg-canvas',
                    )}
                  >
                    <p className="text-xs font-medium text-slate-100">{stage.label}</p>
                    <p className="mt-0.5 text-[10px] leading-tight text-slate-500">{stage.description}</p>
                  </div>
                  {index < (stages.data?.length ?? 0) - 1 && <span className="text-slate-600">→</span>}
                </li>
              )
            })}
          </ol>
        )}
      </Panel>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Panel title="Retrieval settings" description="Applied to this query only unless you save them">
          {pipelines.isLoading ? (
            <LoadingPanel rows={4} />
          ) : (
            <div className="space-y-3">
              <Field label="Pipeline">
                <select className="field" value={pipelineId} onChange={(event) => setPipelineId(event.target.value)}>
                  <option value="">Default pipeline</option>
                  {pipelines.data?.map((pipeline) => (
                    <option key={pipeline.id} value={pipeline.id}>
                      {pipeline.name}
                    </option>
                  ))}
                </select>
              </Field>

              <Field label={`Top K — ${topK}`} hint="How many chunks are passed to the model">
                <input
                  type="range"
                  min={1}
                  max={20}
                  value={topK}
                  onChange={(event) => setTopK(Number(event.target.value))}
                  className="w-full accent-azure-500"
                />
              </Field>

              <Field
                label={`Similarity threshold — ${threshold.toFixed(2)}`}
                hint="Higher is more precise, lower recalls more"
              >
                <input
                  type="range"
                  min={0}
                  max={0.6}
                  step={0.01}
                  value={threshold}
                  onChange={(event) => setThreshold(Number(event.target.value))}
                  className="w-full accent-azure-500"
                />
              </Field>

              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input type="checkbox" checked={rerank} onChange={(event) => setRerank(event.target.checked)} />
                Rerank results
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input type="checkbox" checked={generate} onChange={(event) => setGenerate(event.target.checked)} />
                Generate an answer
              </label>

              {activePipeline && (
                <div className="rounded-md border border-border bg-canvas px-3 py-2 text-[11px] text-slate-400">
                  <p>
                    Chunk size {activePipeline.chunk_size} · overlap {activePipeline.chunk_overlap}
                  </p>
                  <p className="mt-0.5">Embeddings: {activePipeline.embedding_model}</p>
                  {can('documents:write') && (
                    <button
                      type="button"
                      className="btn-ghost mt-2 w-full px-2 py-1 text-[11px]"
                      disabled={savePipeline.isPending}
                      onClick={() =>
                        savePipeline.mutate({
                          top_k: topK,
                          similarity_threshold: threshold,
                          reranking_enabled: rerank,
                        })
                      }
                    >
                      Save these settings to the pipeline
                    </button>
                  )}
                </div>
              )}
            </div>
          )}
        </Panel>

        <Panel className="xl:col-span-2" title="Query playground">
          <textarea
            className="field h-24 resize-y text-sm"
            value={query}
            aria-label="Query"
            onChange={(event) => setQuery(event.target.value)}
          />
          <button
            type="button"
            className="btn-primary mt-2"
            disabled={search.isPending || !query.trim()}
            onClick={() => search.mutate()}
          >
            {search.isPending ? 'Retrieving…' : 'Run query'}
          </button>

          {search.error && <div className="mt-3"><ErrorState error={search.error} /></div>}

          {result && (
            <div className="mt-4 space-y-4">
              <div className="flex flex-wrap gap-2 text-[11px]">
                {result.stages.map((stage) => (
                  <Badge key={stage.stage} tone="info" title={stage.detail}>
                    {stage.stage} · {stage.duration_ms} ms
                  </Badge>
                ))}
                <Badge tone="accent">total {formatDuration(result.latency_ms)}</Badge>
                <Badge tone="neutral">{result.candidates_considered} candidates</Badge>
              </div>

              {result.answer && (
                <div className="rounded-md border border-azure-500/30 bg-azure-500/5 px-3 py-2">
                  <p className="text-[11px] uppercase tracking-wide text-azure-200">Answer</p>
                  <p className="mt-1 whitespace-pre-wrap text-sm text-slate-200">{result.answer}</p>
                </div>
              )}

              {result.chunks.length === 0 ? (
                <EmptyState
                  title="Nothing passed the similarity threshold"
                  description="Lower the threshold, or index a document that covers this topic."
                />
              ) : (
                <ol className="space-y-2">
                  {result.chunks.map((chunk, index) => (
                    <li key={chunk.chunk_id} className="rounded-md border border-border bg-canvas px-3 py-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="text-sm text-slate-200">
                          [{index + 1}] {chunk.document_name}
                          {chunk.page ? ` · page ${chunk.page}` : ''}
                        </span>
                        <span className="flex gap-1">
                          <Badge tone="info">vector {chunk.score.toFixed(3)}</Badge>
                          {chunk.rerank_score !== null && (
                            <Badge tone="accent">reranked {chunk.rerank_score.toFixed(3)}</Badge>
                          )}
                        </span>
                      </div>
                      <p className="mt-1 text-xs leading-relaxed text-slate-400">{chunk.content}</p>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          )}
        </Panel>
      </div>
    </>
  )
}
