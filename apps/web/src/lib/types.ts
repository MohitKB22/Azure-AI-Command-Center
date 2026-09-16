export type Role = 'admin' | 'ai_engineer' | 'developer' | 'analyst' | 'viewer'

export interface User {
  id: string
  email: string
  full_name: string
  role: Role
  team: string | null
  is_active: boolean
  is_demo: boolean
  last_login_at: string | null
  created_at: string
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface ModelEntry {
  id: string
  name: string
  provider: string
  deployment_name: string
  kind: 'chat' | 'embedding'
  context_window: number
  max_output_tokens: number
  capabilities: string[]
  input_cost_per_1k: number
  output_cost_per_1k: number
  currency: string
  status: string
  is_default: boolean
  is_fallback: boolean
  is_demo: boolean
  notes: string | null
  created_at: string
}

export interface Agent {
  id: string
  name: string
  slug: string
  description: string | null
  status: string
  environment: string
  enabled: boolean
  rag_enabled: boolean
  tools: string[]
  tags: string[]
  current_version: number
  model_id: string | null
  is_demo: boolean
  created_at: string
  updated_at: string
}

export interface AgentDetail extends Agent {
  system_prompt: string
  temperature: number
  max_output_tokens: number
  timeout_seconds: number
  max_retries: number
  memory_enabled: boolean
  fallback_model_id: string | null
  rag_pipeline_id: string | null
  guardrail_policy_id: string | null
  model: ModelEntry | null
}

export interface RunStep {
  step_index: number
  node: string
  status: string
  duration_ms: number
  detail: Record<string, unknown>
}

export interface RunSummary {
  id: string
  agent_id: string
  agent_version: number
  status: string
  model_name: string | null
  used_fallback: boolean
  total_tokens: number
  estimated_cost: number
  latency_ms: number
  guardrail_outcome: string
  evaluation_score: number | null
  created_at: string
}

export interface Citation {
  chunk_id: string
  document_id: string
  document_name: string
  page: number | null
  ordinal: number
  score: number
  snippet: string
}

export interface RunDetail extends RunSummary {
  input_text: string
  output_text: string | null
  prompt_tokens: number
  completion_tokens: number
  error_code: string | null
  error_message: string | null
  correlation_id: string | null
  citations: Citation[]
  trace: Record<string, any>
  steps: RunStep[]
}

export interface DocumentSummary {
  id: string
  filename: string
  content_type: string
  size_bytes: number
  status: string
  error_message: string | null
  page_count: number
  chunk_count: number
  version: number
  tags: string[]
  pipeline_id: string | null
  indexed_at: string | null
  is_demo: boolean
  created_at: string
}

export interface DocumentDetail extends DocumentSummary {
  extracted_text_preview: string | null
  doc_metadata: Record<string, unknown>
  storage_uri: string | null
}

export interface Chunk {
  id: string
  ordinal: number
  content: string
  token_estimate: number
  page: number | null
  embedding_model: string | null
}

export interface Pipeline {
  id: string
  name: string
  description: string | null
  chunk_size: number
  chunk_overlap: number
  embedding_model: string
  top_k: number
  similarity_threshold: number
  reranking_enabled: boolean
  metadata_filters: Record<string, unknown>
  is_default: boolean
  is_demo: boolean
  created_at: string
}

export interface RetrievedChunk {
  chunk_id: string
  document_id: string
  document_name: string
  ordinal: number
  page: number | null
  content: string
  score: number
  rerank_score: number | null
}

export interface RagQueryResponse {
  query: string
  answer: string | null
  citations: Citation[]
  chunks: RetrievedChunk[]
  candidates_considered: number
  latency_ms: number
  pipeline: Record<string, any>
  stages: { stage: string; detail: string; duration_ms: number }[]
  run_id: string | null
}

export interface GuardrailPolicy {
  id: string
  name: string
  description: string | null
  detect_prompt_injection: boolean
  redact_pii: boolean
  block_on_injection: boolean
  max_input_chars: number
  banned_phrases: string[]
  tool_allowlist: string[]
  domain_allowlist: string[]
  require_citations: boolean
  is_default: boolean
  created_at: string
}

export interface GuardrailEvent {
  id: string
  run_id: string | null
  stage: string
  rule: string
  severity: string
  action: string
  detail: Record<string, unknown>
  created_at: string
}

export interface Dataset {
  id: string
  name: string
  description: string | null
  items: { question: string; expected_answer?: string }[]
  is_demo: boolean
  created_at: string
}

export interface EvaluationRun {
  id: string
  dataset_id: string
  agent_id: string | null
  status: string
  pass_threshold: number
  aggregate_scores: Record<string, number>
  passed: boolean | null
  regression_detected: boolean
  duration_ms: number
  created_at: string
  results?: EvaluationResult[]
}

export interface EvaluationResult {
  item_index: number
  question: string
  expected: string | null
  answer: string
  scores: Record<string, number>
  passed: boolean
  latency_ms: number
  total_tokens: number
}

export interface Prompt {
  id: string
  key: string
  name: string
  description: string | null
  tags: string[]
  active_version: number
  is_demo: boolean
  created_at: string
  updated_at: string
  versions?: PromptVersion[]
}

export interface PromptVersion {
  id: string
  version: number
  template: string
  variables: string[]
  environment: string
  approval_status: string
  changelog: string | null
  created_at: string
}

export interface AzureResource {
  id: string
  name: string
  resource_type: string
  region: string
  resource_group: string | null
  status: string
  data_source: string
  availability_pct: number
  latency_p95_ms: number
  error_rate_pct: number
  throughput_rpm: number
  quota_used_pct: number | null
  last_checked_at: string | null
  details: Record<string, unknown>
  is_demo: boolean
}

export interface Alert {
  id: string
  title: string
  description: string | null
  severity: string
  source: string
  status: string
  acknowledged_at: string | null
  resolved_at: string | null
  context: Record<string, unknown>
  created_at: string
}

export interface AuditLog {
  id: string
  actor_email: string | null
  action: string
  resource_type: string
  resource_id: string | null
  outcome: string
  request_id: string | null
  changes: Record<string, unknown>
  created_at: string
}

export interface HealthComponent {
  component: string
  status: string
  latency_ms: number
  detail: string
  data_source: string
}

export interface SystemHealth {
  status: string
  environment: string
  demo_mode: boolean
  uptime_seconds: number
  python: string
  providers: Record<string, string>
  components: HealthComponent[]
  requests_24h: number
  error_rate_24h_pct: number
  configuration_warnings: string[]
}

export interface TimeseriesPoint {
  date: string
  requests: number
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  estimated_cost: number
  avg_latency_ms: number
  error_rate_pct: number
}

export interface Overview {
  generated_at: string
  demo_mode: boolean
  environment: string
  providers: Record<string, string>
  kpis: Record<string, number>
  timeseries: TimeseriesPoint[]
  model_usage: { key: string; requests: number; total_tokens: number; estimated_cost: number }[]
  agent_activity: { name: string; runs: number }[]
  recent_runs: RunSummary[]
  active_alerts: Alert[]
  health: SystemHealth
}

export interface CostSummary {
  totals: {
    requests: number
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
    estimated_cost: number
    avg_latency_ms: number
    error_rate_pct: number
  }
  timeseries: TimeseriesPoint[]
  by_model: { key: string; requests: number; total_tokens: number; estimated_cost: number }[]
  by_agent: { key: string; requests: number; total_tokens: number; estimated_cost: number }[]
  by_team: { key: string; requests: number; total_tokens: number; estimated_cost: number }[]
  budgets: {
    id: string
    name: string
    scope: string
    team: string | null
    amount: number
    currency: string
    spent: number
    utilisation_pct: number
    state: 'ok' | 'warning' | 'exceeded'
  }[]
}
