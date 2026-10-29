export interface HistoryItem {
  stem: string
  total: number
  max_points?: number
  unverified?: number
  verified?: number
  pages?: number
  modified: number
}

export interface Health {
  status: string
  ollama_running: boolean
  ollama_url: string
  model: string
  model_available: boolean
  rubric_ready: boolean
  rubric_error: string | null
  sections: string[]
  max_points: number
  max_doc_chars: number
  frontend_built: boolean
  output_dir: string
}

export interface CriterionResult {
  heading?: string
  id: string
  score: number
  evidence?: string
  note?: string
  evidence_verified?: boolean
  evidence_source?: string
  review_hint?: string
  possible_missed_point?: boolean
}

export interface SectionResult {
  criteria: Record<string, { score: number }>
  section_score: number
}

export interface SectionSummary {
  key: string
  label: string
  max: number
  score: number
  criteria: CriterionResult[]
}

export interface Scorecard {
  [key: string]: SectionResult | number
}

export interface JobResult {
  stem: string
  filename: string
  model?: string
  scorecard: Scorecard
  detail: Record<string, unknown>
  sections?: SectionSummary[]
  feedback: string
  reasoning: string
  extraction: { pages: number; ocr_pages: number; characters: number; methods: string[] }
  max_points: number
  unverified_evidence?: number
  recheck?: { attempted: boolean; changed: number; flagged: number }
  missed_point_review?: number
  files: Record<string, string>
}

export interface Job {
  id: string
  filename: string
  status: 'queued' | 'extracting' | 'grading' | 'done' | 'error'
  phase: string
  elapsed: number
  characters: number
  started_at: number
  model?: string
  cancelled?: boolean
  result?: JobResult
  error?: string
  notification?: { status: string; message: string }
  reasoning_length?: number
}

async function request(path: string, init?: RequestInit) {
  const response = await fetch(path, init)
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(detail.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

export const getHealth = () => request('/api/health')
export const getJobs = () => request('/api/jobs')
export const getJob = (id: string) => request(`/api/jobs/${id}`)
export const getResults = () => request('/api/results')
export const getModels = () => request('/api/models')

export interface ComparisonEntry {
  id: string
  heading: string
  score_a: number
  score_b: number
  evidence_a: string
  evidence_b: string
  verified_a: boolean
  verified_b: boolean
  supported_by: string | null
}

export interface ConsensusCriterion {
  id: string
  score: number
  basis: string
}

export interface Comparison {
  run_a: string
  run_b: string
  consensus: {
    score: number
    criteria: ConsensusCriterion[]
    needs_human_review: number
  }
  criteria_compared: number
  agreements: number
  disagreements: ComparisonEntry[]
  agreement_rate: number
  total_a: number
  total_b: number
  total_difference: number
}

export const compareRuns = (a: string, b: string) =>
  request(`/api/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`) as Promise<Comparison>

export async function uploadPdf(
  file: File,
  model?: string,
  recipient?: string,
): Promise<{ job_id: string; filename: string; model: string }> {
  const form = new FormData()
  form.append('file', file)
  if (recipient) form.append('recipient', recipient)
  if (model) form.append('model', model)
  return request('/api/evaluate', { method: 'POST', body: form })
}

export const cancelJob = (jobId: string) =>
  request(`/api/jobs/${jobId}/cancel`, { method: 'POST' })

export async function emailResults(jobId: string, recipient: string) {
  const form = new FormData()
  form.append('job_id', jobId)
  form.append('recipient', recipient)
  return request(`/api/email`, { method: 'POST', body: form })
}

export const downloadUrl = (jobId: string, kind: string) => `/api/jobs/${jobId}/download/${kind}`

export const savedDownloadUrl = (stem: string, kind: string) =>
  `/api/results/${encodeURIComponent(stem)}/${kind}`

export async function openSaved(stem: string): Promise<Job> {
  const response = await fetch(`/api/results/${encodeURIComponent(stem)}`)
  if (!response.ok) throw new Error(`Could not open ${stem}`)
  return response.json() as Promise<Job>
}
