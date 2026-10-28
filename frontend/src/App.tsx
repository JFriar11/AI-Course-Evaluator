import { useCallback, useEffect, useRef, useState } from 'react'
import {
  type Health,
  type HistoryItem,
  type Job,
  cancelJob,
  downloadUrl,
  emailResults,
  getHealth,
  getJobs,
  getModels,
  getResults,
  openSaved,
  savedDownloadUrl,
  uploadPdf,
} from './api'
import ResultPanel from './ResultPanel'
import ComparePanel from './ComparePanel'

type UploadState = { name: string; ok: boolean; message: string }

const THEME_KEY = 'screener-theme'

function initialTheme(): 'dark' | 'light' {
  const stored = localStorage.getItem(THEME_KEY)
  if (stored === 'light' || stored === 'dark') return stored
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

const STATUS_LABEL: Record<string, string> = {
  queued: 'Queued',
  extracting: 'Reading PDF',
  grading: 'AI grading',
  done: 'Complete',
  error: 'Failed',
}

const STATUS_COLOR: Record<string, string> = {
  queued: 'var(--color-muted)',
  extracting: 'var(--color-warning)',
  grading: 'var(--color-accent)',
  done: 'var(--color-success)',
  error: 'var(--color-danger)',
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function clock(seconds: number) {
  if (seconds < 60) return `${seconds}s`
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [jobs, setJobs] = useState<Job[]>([])
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [savedJobs, setSavedJobs] = useState<Job[]>([])
  const [email, setEmail] = useState('')
  const [emailNote, setEmailNote] = useState('')
  const [dragging, setDragging] = useState(false)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [uploads, setUploads] = useState<UploadState[]>([])
  const [models, setModels] = useState<string[]>([])
  const [model, setModel] = useState('')
  const [theme, setTheme] = useState<'dark' | 'light'>(initialTheme)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem(THEME_KEY, theme)
  }, [theme])

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth(null))
    getResults().then(setHistory).catch(() => setHistory([]))
    getModels()
      .then(data => {
        setModels(data.models ?? [])
        setModel(data.default ?? '')
      })
      .catch(() => undefined)
    const stored = localStorage.getItem('delivery-email')
    if (stored) setEmail(stored)
  }, [])

  useEffect(() => {
    const timer = setInterval(() => {
      getJobs().then(setJobs).catch(() => undefined)
    }, 2000)
    return () => clearInterval(timer)
  }, [])

  const refreshHistory = () => getResults().then(setHistory).catch(() => undefined)

  const openReport = async (stem: string) => {
    try {
      const job = await openSaved(stem)
      setSavedJobs(prev => (prev.some(existing => existing.id === job.id) ? prev : [...prev, job]))
      setExpanded(job.id)
    } catch (error) {
      setUploads(prev => [...prev, { name: stem, ok: false, message: String(error) }])
    }
  }

  const addFiles = useCallback(async (raw: FileList | File[]) => {
    for (const file of Array.from(raw)) {
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        setUploads(prev => [...prev, { name: file.name, ok: false, message: 'Only PDF files can be graded.' }])
        continue
      }
      try {
        await uploadPdf(file, model)
        setUploads(prev => [...prev, { name: file.name, ok: true, message: `Queued for grading with ${model}.` }])
      } catch (error) {
        setUploads(prev => [...prev, { name: file.name, ok: false, message: String(error) }])
      }
    }
  }, [model])

  const onDrop = (event: React.DragEvent) => {
    event.preventDefault()
    setDragging(false)
    if (event.dataTransfer.files.length) addFiles(event.dataTransfer.files)
  }

  const saveEmail = () => {
    const value = email.trim()
    if (!value) return
    localStorage.setItem('delivery-email', value)
    setEmailNote(`Saved. Results can be emailed to ${value}.`)
  }

  const sendEmail = async (jobId: string) => {
    const value = email.trim()
    if (!value) {
      setEmailNote('Enter a delivery email first.')
      return
    }
    try {
      const response = await emailResults(jobId, value)
      setEmailNote(response.status === 'sent' ? `Sent to ${value}.` : response.message)
    } catch (error) {
      setEmailNote(`Could not send: ${String(error)}`)
    }
  }

  const active = jobs.filter(job => job.status !== 'done' && job.status !== 'error')
  const completed = jobs.filter(job => job.status === 'done')
  const cancelled = jobs.filter(job => job.cancelled)
  const failed = jobs.filter(job => job.status === 'error' && !job.cancelled)
  const selected = [...jobs, ...savedJobs].find(job => job.id === expanded) ?? null

  const modelLabel = health ? health.model : 'not connected'
  const online = health?.ollama_running && health?.model_available && health?.rubric_ready

  return (
    <div className="min-h-screen" style={{ background: 'var(--color-bg)', fontFamily: 'var(--font-body)' }}>
      <header style={{ borderBottom: '1px solid var(--color-border)', background: 'var(--color-surface)' }}>
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <img src="/logo-mark.png" alt="Scarlet Hawk Evaluator logo" width="44" height="44"
              style={{ display: 'block' }} />
            <div style={{ display: 'grid', lineHeight: 1.25 }}>
              <span className="text-base font-semibold tracking-wide" style={{ fontFamily: 'var(--font-display)', color: 'var(--color-text)' }}>
                Scarlet Hawk
              </span>
              <span className="text-xs tracking-widest uppercase" style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-muted)' }}>
                Evaluator
              </span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="theme-toggle" role="group" aria-label="Colour theme">
              <button type="button" aria-pressed={theme === 'dark'} onClick={() => setTheme('dark')}>
                Dark
              </button>
              <button type="button" aria-pressed={theme === 'light'} onClick={() => setTheme('light')}>
                Light
              </button>
            </div>
            <span
              className="text-xs px-2 py-1 rounded flex items-center gap-2"
              style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-muted)', background: 'var(--color-surface-2)', border: '1px solid var(--color-border)' }}
            >
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: online ? 'var(--color-success)' : 'var(--color-danger)' }} />
              {online ? `${modelLabel} · ready` : 'model offline'}
            </span>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-10 grid gap-8">
        <div>
          <h1 className="text-3xl font-semibold mb-1 leading-tight" style={{ fontFamily: 'var(--font-display)', color: 'var(--color-text)' }}>
            Program Assessment Reports
          </h1>
          <p className="text-sm" style={{ color: 'var(--color-muted)' }}>
            Drop a report PDF. The local model scores all 23 rubric criteria and shows the evidence behind each score.
          </p>
        </div>

        {health && !online && (
          <div className="rounded-xl p-4" style={{ border: '1px solid var(--color-danger)', background: 'rgba(255,51,51,0.08)' }}>
            <p className="text-sm font-semibold" style={{ color: 'var(--color-danger)' }}>Setup problem</p>
            {!health.ollama_running && (
              <p className="text-xs mt-1" style={{ color: 'var(--color-muted)', fontFamily: 'var(--font-mono)' }}>
                Ollama is not running at {health.ollama_url}. Start it with: ollama serve
              </p>
            )}
            {health.ollama_running && !health.model_available && (
              <p className="text-xs mt-1" style={{ color: 'var(--color-muted)', fontFamily: 'var(--font-mono)' }}>
                Model {health.model} is not installed. Run: ollama pull {health.model}
              </p>
            )}
            {health.rubric_ready === false && (
              <p className="text-xs mt-1" style={{ color: 'var(--color-muted)', fontFamily: 'var(--font-mono)' }}>
                Rubric error: {health.rubric_error}
              </p>
            )}
          </div>
        )}

        <div className="grid lg:grid-cols-[1fr_300px] gap-6">
          <div className="flex flex-col gap-6">
            <div
              onDragOver={event => { event.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              onClick={() => inputRef.current?.click()}
              className="rounded-xl cursor-pointer transition-all duration-200 select-none"
              style={{
                border: `2px dashed ${dragging ? 'var(--color-accent)' : 'var(--color-border)'}`,
                background: dragging ? 'rgba(204,0,0,0.06)' : 'var(--color-surface)',
                padding: '36px 32px',
              }}
            >
              <input ref={inputRef} type="file" multiple accept="application/pdf,.pdf" className="hidden"
                onChange={event => { if (event.target.files?.length) addFiles(event.target.files) }} />
              <div className="flex flex-col items-center gap-3 text-center">
                <div className="w-12 h-12 rounded-xl flex items-center justify-center"
                  style={{ background: dragging ? 'var(--color-accent-dim)' : 'var(--color-surface-2)' }}>
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={dragging ? 'var(--color-accent)' : 'var(--color-muted)'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                    <polyline points="17 8 12 3 7 8" />
                    <line x1="12" y1="3" x2="12" y2="15" />
                  </svg>
                </div>
                <div>
                  <p className="text-sm font-medium" style={{ color: 'var(--color-text)' }}>
                    Drop report PDFs here or <span style={{ color: 'var(--color-accent)' }}>browse</span>
                  </p>
                  <p className="text-xs mt-1" style={{ color: 'var(--color-muted)', fontFamily: 'var(--font-mono)' }}>
                    grading runs locally · up to {health?.max_doc_chars?.toLocaleString() ?? '25,000'} characters per report
                  </p>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-3 flex-wrap">
              <label className="text-xs font-medium" style={{ color: 'var(--color-muted)', fontFamily: 'var(--font-mono)' }}>
                Model
              </label>
              <select
                value={model}
                onChange={event => setModel(event.target.value)}
                className="text-xs"
                style={{
                  background: 'var(--color-surface)',
                  color: 'var(--color-text)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 6,
                  padding: '6px 10px',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                {models.length === 0 && <option value={model}>{model || 'no models installed'}</option>}
                {models.map(name => <option key={name} value={name}>{name}</option>)}
              </select>
              <span className="text-xs" style={{ color: 'var(--color-muted)', fontFamily: 'var(--font-mono)' }}>
                smaller models finish faster · a 10-page report takes roughly 5-20 minutes
              </span>
            </div>

            {uploads.length > 0 && (
              <div className="flex flex-col gap-2">
                {uploads.map((upload, index) => (
                  <p key={index} className="text-xs" style={{ color: upload.ok ? 'var(--color-success)' : 'var(--color-danger)', fontFamily: 'var(--font-mono)' }}>
                    {upload.name}: {upload.message}
                  </p>
                ))}
              </div>
            )}

            {jobs.length > 0 && (
              <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--color-border)', background: 'var(--color-surface)' }}>
                <div className="px-5 py-3 flex items-center justify-between" style={{ borderBottom: '1px solid var(--color-border)' }}>
                  <span className="text-xs font-medium" style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-muted)' }}>
                    REPORTS · {jobs.length}
                  </span>
                  <div className="flex gap-4 text-xs" style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-muted)' }}>
                    {active.length > 0 && <span style={{ color: 'var(--color-warning)' }}>{active.length} in progress</span>}
                    {completed.length > 0 && <span style={{ color: 'var(--color-success)' }}>{completed.length} done</span>}
                    {failed.length > 0 && <span style={{ color: 'var(--color-danger)' }}>{failed.length} failed</span>}
                  </div>
                </div>

                <div className="scrollable overflow-y-auto" style={{ maxHeight: 420 }}>
                  {jobs.map((job, index) => (
                    <div key={job.id} className="px-5 py-4 flex items-center gap-4"
                      style={{ borderBottom: index < jobs.length - 1 ? '1px solid var(--color-border)' : 'none' }}>
                      <div className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 text-xs font-bold"
                        style={{ background: 'var(--color-surface-2)', color: 'var(--color-accent)', fontFamily: 'var(--font-mono)' }}>
                        PDF
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2 mb-1.5">
                          <button
                            type="button"
                            onClick={() => setExpanded(expanded === job.id ? null : job.id)}
                            className="text-sm font-medium truncate text-left"
                            style={{ color: 'var(--color-text)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
                          >
                            {job.filename}
                          </button>
                          <div className="flex items-center gap-1.5 flex-shrink-0">
                            <span className="w-1.5 h-1.5 rounded-full" style={{ background: job.cancelled && job.status === 'error' ? 'var(--color-muted)' : STATUS_COLOR[job.status] }} />
                            <span className="text-xs" style={{ color: job.cancelled && job.status === 'error' ? 'var(--color-muted)' : STATUS_COLOR[job.status], fontFamily: 'var(--font-mono)' }}>
                              {job.cancelled && job.status === 'error' ? 'Cancelled' : (STATUS_LABEL[job.status] ?? job.status)}
                            </span>
                          </div>
                        </div>

                        {job.status === 'done' && job.result && (
                          <div className="flex gap-3 mt-1.5 flex-wrap">
                            <span className="text-xs" style={{ color: 'var(--color-muted)', fontFamily: 'var(--font-mono)' }}>
                              {job.result.extraction.pages} pages
                            </span>
                            <span className="text-xs font-semibold" style={{ color: 'var(--color-success)', fontFamily: 'var(--font-mono)' }}>
                              {Number(job.result.scorecard.total_calculated_score)} / {job.result.max_points}
                            </span>
                            <a href={downloadUrl(job.id, 'feedback')} className="text-xs underline underline-offset-2" style={{ color: 'var(--color-accent)', fontFamily: 'var(--font-mono)' }}>
                              feedback →
                            </a>
                            <a href={downloadUrl(job.id, 'scorecard')} className="text-xs underline underline-offset-2" style={{ color: 'var(--color-accent)', fontFamily: 'var(--font-mono)' }}>
                              scorecard →
                            </a>
                          </div>
                        )}

                        {job.status === 'error' && (
                          <p className="text-xs mt-1" style={{ color: 'var(--color-danger)' }}>{job.error ?? job.phase}</p>
                        )}

                        {(job.status === 'extracting' || job.status === 'grading' || job.status === 'queued') && (
                          <div className="flex items-center gap-3 mt-1.5">
                            <div className="h-1 rounded-full overflow-hidden flex-1" style={{ background: 'var(--color-surface-2)' }}>
                              <div className={job.status === 'queued' ? 'h-full' : 'h-full sweep'}
                                style={{ width: job.status === 'queued' ? '8%' : '100%' }} />
                            </div>
                            <span className="text-xs" style={{ color: 'var(--color-muted)', fontFamily: 'var(--font-mono)' }}>
                              {clock(job.elapsed)} · {job.characters.toLocaleString()} chars
                            </span>
                            <button
                              type="button"
                              onClick={() => cancelJob(job.id).catch(() => undefined)}
                              className="text-xs"
                              style={{
                                color: 'var(--color-danger)',
                                background: 'none',
                                border: '1px solid var(--color-border)',
                                borderRadius: 6,
                                padding: '4px 8px',
                                cursor: 'pointer',
                                fontFamily: 'var(--font-mono)',
                              }}
                            >
                              stop
                            </button>
                          </div>
                        )}

                        {job.status !== 'done' && job.status !== 'error' && (
                          <div className="flex gap-3 mt-1.5">
                            <span className="text-xs" style={{ color: 'var(--color-label)', fontFamily: 'var(--font-mono)' }}>{job.phase}</span>
                            <span className="text-xs" style={{ color: 'var(--color-label)', fontFamily: 'var(--font-mono)' }}>{clock(job.elapsed)}</span>
                            {job.characters > 0 && (
                              <span className="text-xs" style={{ color: 'var(--color-label)', fontFamily: 'var(--font-mono)' }}>
                                {job.characters.toLocaleString()} chars received
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {selected?.status === 'done' && (
              <div className="flex flex-col gap-4">
                <ResultPanel job={selected} />
                <ComparePanel stems={history.map((item) => item.stem)} />
                <div className="flex gap-3 items-center flex-wrap">
                  <button
                    type="button"
                    onClick={() => sendEmail(selected.id)}
                    className="rounded-lg py-2.5 text-sm font-semibold"
                    style={{ background: 'var(--color-accent)', color: '#fff', border: 'none', fontFamily: 'var(--font-display)', cursor: 'pointer' }}
                  >
                    Email this report
                  </button>
                  <button
                    type="button"
                    onClick={() => setExpanded(null)}
                    className="rounded-lg py-2.5 text-sm"
                    style={{ background: 'var(--color-surface-2)', color: 'var(--color-muted)', border: '1px solid var(--color-border)', cursor: 'pointer' }}
                  >
                    Close
                  </button>
                </div>
              </div>
            )}

            {jobs.length === 0 && history.length === 0 && (
              <div className="text-center py-4">
                <p className="text-xs" style={{ color: 'var(--color-label)', fontFamily: 'var(--font-mono)' }}>
                  No reports yet — drop a PDF above to begin
                </p>
              </div>
            )}

            {history.length > 0 && (
              <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--color-border)', background: 'var(--color-surface)' }}>
                <div className="px-5 py-3 flex items-center gap-2" style={{ borderBottom: '1px solid var(--color-border)' }}>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="9 11 12 14 22 4" />
                    <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
                  </svg>
                  <span className="text-xs font-semibold" style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-muted)' }}>
                    PREVIOUSLY GRADED
                  </span>
                  <span className="ml-auto text-xs px-1.5 py-0.5 rounded" style={{ background: 'var(--color-accent-dim)', color: 'var(--color-accent)', fontFamily: 'var(--font-mono)' }}>
                    {history.length}
                  </span>
                </div>
                <div className="scrollable overflow-y-auto" style={{ maxHeight: 260 }}>
                  {history.map((item, index) => (
                    <div key={item.stem} className="px-5 py-3 flex items-center gap-3"
                      style={{ borderBottom: index < history.length - 1 ? '1px solid var(--color-border)' : 'none' }}>
                      <div className="flex-1 min-w-0">
                        <button type="button" onClick={() => openReport(item.stem)}
                          className="text-sm truncate text-left"
                          style={{ color: 'var(--color-text)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                          {item.stem}
                        </button>
                        <p className="text-xs mt-0.5" style={{ color: 'var(--color-muted)', fontFamily: 'var(--font-mono)' }}>
                          {item.total ?? 0} / {item.max_points ?? 23}
                          {item.unverified ? ` · ${item.unverified} unverified quote(s)` : ''}
                        </p>
                      </div>
                      <div className="flex gap-2 flex-shrink-0">
                        <a href={savedDownloadUrl(item.stem, 'feedback')} className="text-xs px-2 py-1 rounded" style={{ background: 'var(--color-surface-2)', color: 'var(--color-text)', fontFamily: 'var(--font-mono)', textDecoration: 'none' }}>feedback</a>
                        <a href={savedDownloadUrl(item.stem, 'scorecard')} className="text-xs px-2 py-1 rounded" style={{ background: 'var(--color-surface-2)', color: 'var(--color-text)', fontFamily: 'var(--font-mono)', textDecoration: 'none' }}>json</a>
                      </div>
                    </div>
                  ))}
                </div>
                <p className="px-5 py-2 text-xs" style={{ color: 'var(--color-label)', fontFamily: 'var(--font-mono)' }}>
                  saved in {health?.output_dir ?? 'Output/'}
                </p>
              </div>
            )}
          </div>

          <div className="flex flex-col gap-5">
            <div className="rounded-xl p-5" style={{ border: '1px solid var(--color-border)', background: 'var(--color-surface)' }}>
              <div className="flex items-center gap-2 mb-4">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
                  <polyline points="22,6 12,13 2,6" />
                </svg>
                <span className="text-xs font-semibold" style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-muted)' }}>DELIVERY EMAIL</span>
              </div>
              <input
                type="email"
                value={email}
                onChange={event => { setEmail(event.target.value); setEmailNote('') }}
                onKeyDown={event => event.key === 'Enter' && saveEmail()}
                placeholder="you@example.com"
                className="w-full rounded-lg px-3 py-2.5 text-sm outline-none"
                style={{ background: 'var(--color-surface-2)', border: '1px solid var(--color-border)', color: 'var(--color-text)', fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}
              />
              <button
                type="button"
                onClick={saveEmail}
                disabled={!email.trim()}
                className="mt-3 w-full rounded-lg py-2.5 text-sm font-semibold"
                style={{
                  background: email.trim() ? 'var(--color-accent)' : 'var(--color-surface-2)',
                  color: email.trim() ? '#fff' : 'var(--color-muted)',
                  fontFamily: 'var(--font-display)',
                  cursor: email.trim() ? 'pointer' : 'not-allowed',
                  border: 'none',
                }}
              >
                Save email
              </button>
              {emailNote && (
                <p className="mt-2 text-xs" style={{ color: 'var(--color-success)', fontFamily: 'var(--font-mono)' }}>{emailNote}</p>
              )}
              <p className="mt-2 text-xs" style={{ color: 'var(--color-label)', fontFamily: 'var(--font-mono)' }}>
                sending needs backend/email_config.json (SMTP host, port, user, password)
              </p>
            </div>

            <div className="rounded-xl p-5" style={{ border: '1px solid var(--color-border)', background: 'var(--color-surface)' }}>
              <div className="flex items-center gap-2 mb-4">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
                <span className="text-xs font-semibold" style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-muted)' }}>AGENT STATUS</span>
              </div>
              <div className="flex flex-col gap-2.5">
                <StatusRow label="Model" value={modelLabel} dot={health?.model_available ? 'var(--color-success)' : 'var(--color-danger)'} />
                <StatusRow label="Ollama" value={health?.ollama_running ? 'connected' : 'offline'} dot={health?.ollama_running ? 'var(--color-success)' : 'var(--color-danger)'} />
                <StatusRow label="Rubric" value={health?.rubric_ready ? `${(health?.sections ?? []).length} sections · 23 criteria` : 'missing'} dot={health?.rubric_ready ? 'var(--color-success)' : 'var(--color-danger)'} />
                <StatusRow label="In progress" value={`${active.length}`} dot="var(--color-warning)" />
                <StatusRow label="Completed" value={`${completed.length}`} dot="var(--color-success)" />
              </div>
            </div>

            <div className="rounded-xl p-5" style={{ border: '1px solid var(--color-border)', background: 'var(--color-surface)' }}>
              <p className="text-xs font-semibold mb-3" style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-muted)' }}>HOW IT WORKS</p>
              <ol className="flex flex-col gap-2.5">
                {[
                  'Drop a program assessment PDF.',
                  'Text is extracted page by page; scanned pages use OCR.',
                  'The local model scores each of the 23 criteria with quoted evidence.',
                  'Totals are recomputed and the scorecard, feedback and audit trail are saved.',
                ].map((step, index) => (
                  <li key={index} className="flex gap-3 items-start">
                    <span className="w-4 h-4 rounded flex items-center justify-center text-xs flex-shrink-0 mt-0.5"
                      style={{ background: 'var(--color-accent-dim)', color: 'var(--color-accent)', fontFamily: 'var(--font-mono)', fontSize: '0.65rem', fontWeight: 600 }}>
                      {index + 1}
                    </span>
                    <span className="text-xs leading-relaxed" style={{ color: 'var(--color-muted)' }}>{step}</span>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </div>
      </main>

      <footer style={{ borderTop: '1px solid var(--color-border)', background: 'var(--color-surface)' }}>
        <div className="max-w-5xl mx-auto px-6 py-5 flex items-center justify-between gap-4 flex-wrap">
          <img src="/logo.png" alt="Scarlet Hawk Evaluator" width="180"
            style={{ display: 'block' }} />
          <span className="text-xs" style={{ color: 'var(--color-muted)', fontFamily: 'var(--font-mono)' }}>
            Runs locally · no report leaves this machine
          </span>
        </div>
      </footer>
    </div>
  )
}

function StatusRow({ label, value, dot }: { label: string; value: string; dot: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs" style={{ color: 'var(--color-muted)', fontFamily: 'var(--font-mono)' }}>{label}</span>
      <div className="flex items-center gap-1.5">
        <span className="w-1.5 h-1.5 rounded-full" style={{ background: dot }} />
        <span className="text-xs" style={{ color: 'var(--color-text)', fontFamily: 'var(--font-mono)' }}>{value}</span>
      </div>
    </div>
  )
}
