import { useState, useRef, useCallback } from 'react'

type FileStatus = 'queued' | 'processing' | 'done' | 'error'

interface ReviewFile {
  id: string
  name: string
  size: number
  type: string
  status: FileStatus
  progress: number
  addedAt: Date
  reviewLink?: string
}

const statusConfig: Record<FileStatus, { label: string; color: string; dot: string }> = {
  queued:     { label: 'Queued',     color: 'text-[var(--color-muted)]',   dot: 'bg-[var(--color-muted)]' },
  processing: { label: 'Processing', color: 'text-[var(--color-warning)]', dot: 'bg-[var(--color-warning)] animate-pulse' },
  done:       { label: 'Done',       color: 'text-[var(--color-success)]', dot: 'bg-[var(--color-success)]' },
  error:      { label: 'Error',      color: 'text-[var(--color-danger)]',  dot: 'bg-[var(--color-danger)]' },
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatTime(date: Date) {
  return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
}

let idCounter = 1
const mockProcess = (file: ReviewFile, update: (id: string, patch: Partial<ReviewFile>) => void) => {
  let progress = 0
  const interval = setInterval(() => {
    progress += Math.random() * 18 + 5
    if (progress >= 100) {
      clearInterval(interval)
      update(file.id, {
        status: 'done',
        progress: 100,
        reviewLink: `https://review.local/files/${file.id}`,
      })
    } else {
      update(file.id, { status: 'processing', progress })
    }
  }, 400)
}

export default function App() {
  const [files, setFiles] = useState<ReviewFile[]>([])
  const [email, setEmail] = useState('')
  const [emailSaved, setEmailSaved] = useState(false)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const updateFile = useCallback((id: string, patch: Partial<ReviewFile>) => {
    setFiles(prev => prev.map(f => f.id === id ? { ...f, ...patch } : f))
  }, [])

  const addFiles = (rawFiles: FileList | File[]) => {
    const incoming: ReviewFile[] = Array.from(rawFiles).map(f => ({
      id: `file-${idCounter++}`,
      name: f.name,
      size: f.size,
      type: f.type || 'application/octet-stream',
      status: 'queued',
      progress: 0,
      addedAt: new Date(),
    }))
    setFiles(prev => [...prev, ...incoming])
    setTimeout(() => {
      incoming.forEach(f => mockProcess(f, updateFile))
    }, 600)
  }

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files)
  }

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.length) addFiles(e.target.files)
  }

  const saveEmail = () => {
    if (email.trim()) setEmailSaved(true)
  }

  const queued = files.filter(f => f.status === 'queued').length
  const processing = files.filter(f => f.status === 'processing').length
  const done = files.filter(f => f.status === 'done').length

  return (
    <div className="min-h-screen" style={{ background: 'var(--color-bg)', fontFamily: 'var(--font-body)' }}>
      {/* Header */}
      <header style={{ borderBottom: '1px solid var(--color-border)', background: 'var(--color-surface)' }}>
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className="w-8 h-8 rounded flex items-center justify-center text-white font-bold text-sm"
              style={{ background: 'var(--color-accent)', fontFamily: 'var(--font-display)' }}
            >
              R
            </div>
            <span className="text-base font-semibold tracking-wide" style={{ fontFamily: 'var(--font-display)', color: 'var(--color-text)' }}>
              ReviewAgent
            </span>
          </div>
          <span
            className="text-xs px-2 py-1 rounded"
            style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-muted)', background: 'var(--color-surface-2)', border: '1px solid var(--color-border)' }}
          >
            local · agent online
          </span>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-10 grid gap-8">
        {/* Hero row */}
        <div>
          <h1 className="text-3xl font-semibold mb-1 leading-tight" style={{ fontFamily: 'var(--font-display)', color: 'var(--color-text)' }}>
            File Review Dashboard
          </h1>
          <p className="text-sm" style={{ color: 'var(--color-muted)' }}>
            Upload documents — the local AI agent reviews them and emails you a link to the edited versions.
          </p>
        </div>

        <div className="grid lg:grid-cols-[1fr_300px] gap-6">
          {/* Left column */}
          <div className="flex flex-col gap-6">
            {/* Drop zone */}
            <div
              onDragOver={e => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              onClick={() => inputRef.current?.click()}
              className="rounded-xl cursor-pointer transition-all duration-200 select-none"
              style={{
                border: `2px dashed ${dragging ? 'var(--color-accent)' : 'var(--color-border)'}`,
                background: dragging ? 'rgba(79,142,247,0.06)' : 'var(--color-surface)',
                padding: '40px 32px',
              }}
            >
              <input ref={inputRef} type="file" multiple className="hidden" onChange={onInputChange} />
              <div className="flex flex-col items-center gap-3 text-center">
                <div
                  className="w-12 h-12 rounded-xl flex items-center justify-center"
                  style={{ background: dragging ? 'var(--color-accent-dim)' : 'var(--color-surface-2)' }}
                >
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={dragging ? 'var(--color-accent)' : 'var(--color-muted)'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                    <polyline points="17 8 12 3 7 8"/>
                    <line x1="12" y1="3" x2="12" y2="15"/>
                  </svg>
                </div>
                <div>
                  <p className="text-sm font-medium" style={{ color: 'var(--color-text)' }}>
                    Drop files here or <span style={{ color: 'var(--color-accent)' }}>browse</span>
                  </p>
                  <p className="text-xs mt-1" style={{ color: 'var(--color-muted)', fontFamily: 'var(--font-mono)' }}>
                    PDF · DOCX · TXT · MD · any format
                  </p>
                </div>
              </div>
            </div>

            {/* File list */}
            {files.length > 0 && (
              <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--color-border)', background: 'var(--color-surface)' }}>
                <div className="px-5 py-3 flex items-center justify-between" style={{ borderBottom: '1px solid var(--color-border)' }}>
                  <span className="text-xs font-medium" style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-muted)' }}>
                    FILES · {files.length}
                  </span>
                  <div className="flex gap-4 text-xs" style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-muted)' }}>
                    {queued > 0 && <span>{queued} queued</span>}
                    {processing > 0 && <span style={{ color: 'var(--color-warning)' }}>{processing} processing</span>}
                    {done > 0 && <span style={{ color: 'var(--color-success)' }}>{done} done</span>}
                  </div>
                </div>
                <div className="scrollable overflow-y-auto" style={{ maxHeight: 360 }}>
                  {files.map((f, i) => (
                    <div
                      key={f.id}
                      className="px-5 py-4 flex items-center gap-4"
                      style={{ borderBottom: i < files.length - 1 ? '1px solid var(--color-border)' : 'none' }}
                    >
                      {/* File icon */}
                      <div
                        className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 text-xs font-bold"
                        style={{ background: 'var(--color-surface-2)', color: 'var(--color-accent)', fontFamily: 'var(--font-mono)' }}
                      >
                        {f.name.split('.').pop()?.toUpperCase().slice(0, 4) || 'FILE'}
                      </div>

                      {/* Name + progress */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2 mb-1.5">
                          <span className="text-sm font-medium truncate" style={{ color: 'var(--color-text)' }}>{f.name}</span>
                          <div className="flex items-center gap-1.5 flex-shrink-0">
                            <span className={`w-1.5 h-1.5 rounded-full ${statusConfig[f.status].dot}`} />
                            <span className={`text-xs ${statusConfig[f.status].color}`} style={{ fontFamily: 'var(--font-mono)' }}>
                              {statusConfig[f.status].label}
                            </span>
                          </div>
                        </div>
                        {/* Progress bar */}
                        {(f.status === 'processing' || f.status === 'queued') && (
                          <div className="h-1 rounded-full overflow-hidden" style={{ background: 'var(--color-surface-2)' }}>
                            <div
                              className="h-full rounded-full transition-all duration-300"
                              style={{
                                width: `${f.progress}%`,
                                background: f.status === 'processing' ? 'var(--color-accent)' : 'var(--color-border)',
                              }}
                            />
                          </div>
                        )}
                        {f.status === 'done' && (
                          <div className="h-1 rounded-full" style={{ background: 'var(--color-success)', width: '100%', opacity: 0.5 }} />
                        )}
                        <div className="flex gap-3 mt-1.5">
                          <span className="text-xs" style={{ color: 'var(--color-label)', fontFamily: 'var(--font-mono)' }}>{formatSize(f.size)}</span>
                          <span className="text-xs" style={{ color: 'var(--color-label)', fontFamily: 'var(--font-mono)' }}>{formatTime(f.addedAt)}</span>
                          {f.reviewLink && (
                            <a
                              href={f.reviewLink}
                              target="_blank"
                              rel="noreferrer"
                              className="text-xs underline underline-offset-2 transition-opacity hover:opacity-70"
                              style={{ color: 'var(--color-accent)', fontFamily: 'var(--font-mono)' }}
                            >
                              view edit →
                            </a>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {files.length === 0 && (
              <div className="text-center py-4">
                <p className="text-xs" style={{ color: 'var(--color-label)', fontFamily: 'var(--font-mono)' }}>
                  No files yet — drop some above to begin
                </p>
              </div>
            )}

            {/* Agent outputs */}
            <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--color-border)', background: 'var(--color-surface)' }}>
              <div className="px-5 py-3 flex items-center gap-2" style={{ borderBottom: '1px solid var(--color-border)' }}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="9 11 12 14 22 4"/>
                  <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>
                </svg>
                <span className="text-xs font-semibold" style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-muted)' }}>
                  AGENT OUTPUTS
                </span>
                {done > 0 && (
                  <span
                    className="ml-auto text-xs px-1.5 py-0.5 rounded"
                    style={{ background: 'var(--color-accent-dim)', color: 'var(--color-accent)', fontFamily: 'var(--font-mono)' }}
                  >
                    {done}
                  </span>
                )}
              </div>

              <div className="scrollable overflow-y-auto" style={{ minHeight: 120, maxHeight: 280 }}>
                {files.length === 0 && (
                  <div className="flex flex-col items-center justify-center h-28 gap-2">
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'var(--color-surface-2)' }}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-label)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                        <polyline points="14 2 14 8 20 8"/>
                      </svg>
                    </div>
                    <p className="text-xs" style={{ color: 'var(--color-label)', fontFamily: 'var(--font-mono)' }}>
                      outputs appear here once processed
                    </p>
                  </div>
                )}

                {files.length > 0 && files.every(f => f.status === 'queued') && (
                  <div className="flex items-center justify-center h-28">
                    <p className="text-xs" style={{ color: 'var(--color-label)', fontFamily: 'var(--font-mono)' }}>
                      waiting for agent to begin…
                    </p>
                  </div>
                )}

                {files.filter(f => f.status === 'processing' || f.status === 'done' || f.status === 'error').map((f, i, arr) => (
                  <div
                    key={f.id}
                    className="px-5 py-3 flex items-center gap-3"
                    style={{ borderBottom: i < arr.length - 1 ? '1px solid var(--color-border)' : 'none' }}
                  >
                    {/* status icon */}
                    {f.status === 'done' && (
                      <div className="w-6 h-6 rounded flex items-center justify-center flex-shrink-0" style={{ background: 'rgba(34,197,94,0.12)' }}>
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--color-success)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="20 6 9 17 4 12"/>
                        </svg>
                      </div>
                    )}
                    {f.status === 'processing' && (
                      <div className="w-6 h-6 rounded flex items-center justify-center flex-shrink-0" style={{ background: 'rgba(245,158,11,0.12)' }}>
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--color-warning)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="animate-spin">
                          <path d="M21 12a9 9 0 11-6.219-8.56"/>
                        </svg>
                      </div>
                    )}
                    {f.status === 'error' && (
                      <div className="w-6 h-6 rounded flex items-center justify-center flex-shrink-0" style={{ background: 'rgba(239,68,68,0.12)' }}>
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--color-danger)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                        </svg>
                      </div>
                    )}

                    <div className="flex-1 min-w-0">
                      <p className="text-sm truncate" style={{ color: 'var(--color-text)' }}>{f.name}</p>
                      <p className="text-xs mt-0.5" style={{ color: 'var(--color-muted)', fontFamily: 'var(--font-mono)' }}>
                        {f.status === 'processing' && `reviewing… ${Math.round(f.progress)}%`}
                        {f.status === 'done' && 'review complete'}
                        {f.status === 'error' && 'agent error'}
                      </p>
                    </div>

                    {f.reviewLink && (
                      <a
                        href={f.reviewLink}
                        target="_blank"
                        rel="noreferrer"
                        className="flex-shrink-0 text-xs px-2.5 py-1.5 rounded-lg font-medium transition-opacity hover:opacity-80"
                        style={{ background: 'var(--color-accent-dim)', color: 'var(--color-accent)', fontFamily: 'var(--font-mono)', textDecoration: 'none' }}
                      >
                        download →
                      </a>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Right column */}
          <div className="flex flex-col gap-5">
            {/* Email config */}
            <div className="rounded-xl p-5" style={{ border: '1px solid var(--color-border)', background: 'var(--color-surface)' }}>
              <div className="flex items-center gap-2 mb-4">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
                  <polyline points="22,6 12,13 2,6"/>
                </svg>
                <span className="text-xs font-semibold" style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-muted)' }}>DELIVERY EMAIL</span>
              </div>
              <input
                type="email"
                value={email}
                onChange={e => { setEmail(e.target.value); setEmailSaved(false) }}
                onKeyDown={e => e.key === 'Enter' && saveEmail()}
                placeholder="you@example.com"
                className="w-full rounded-lg px-3 py-2.5 text-sm outline-none transition-all"
                style={{
                  background: 'var(--color-surface-2)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.8rem',
                }}
                onFocus={e => { e.target.style.borderColor = 'var(--color-accent)' }}
                onBlur={e => { e.target.style.borderColor = 'var(--color-border)' }}
              />
              <button
                onClick={saveEmail}
                disabled={!email.trim()}
                className="mt-3 w-full rounded-lg py-2.5 text-sm font-semibold transition-all duration-150"
                style={{
                  background: email.trim() ? 'var(--color-accent)' : 'var(--color-surface-2)',
                  color: email.trim() ? '#fff' : 'var(--color-muted)',
                  fontFamily: 'var(--font-display)',
                  cursor: email.trim() ? 'pointer' : 'not-allowed',
                  border: 'none',
                }}
              >
                {emailSaved ? '✓ Saved' : 'Save email'}
              </button>
              {emailSaved && (
                <p className="mt-2 text-xs text-center" style={{ color: 'var(--color-success)', fontFamily: 'var(--font-mono)' }}>
                  Results will be emailed to {email}
                </p>
              )}
            </div>

            {/* Agent status */}
            <div className="rounded-xl p-5" style={{ border: '1px solid var(--color-border)', background: 'var(--color-surface)' }}>
              <div className="flex items-center gap-2 mb-4">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10"/>
                  <line x1="12" y1="8" x2="12" y2="12"/>
                  <line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
                <span className="text-xs font-semibold" style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-muted)' }}>AGENT STATUS</span>
              </div>
              <div className="flex flex-col gap-2.5">
                <StatusRow label="Agent" value="online" dot="var(--color-success)" />
                <StatusRow label="Model" value="local · llama3" dot="var(--color-accent)" />
                <StatusRow label="Queue" value={`${files.filter(f => f.status !== 'done').length} pending`} dot="var(--color-warning)" />
                <StatusRow label="Completed" value={`${done} file${done !== 1 ? 's' : ''}`} dot="var(--color-success)" />
              </div>
            </div>

            {/* How it works */}
            <div className="rounded-xl p-5" style={{ border: '1px solid var(--color-border)', background: 'var(--color-surface)' }}>
              <p className="text-xs font-semibold mb-3" style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-muted)' }}>HOW IT WORKS</p>
              <ol className="flex flex-col gap-2.5">
                {[
                  'Upload files via drag & drop',
                  'Local AI agent reviews & edits each file',
                  'You receive an email with a download link',
                ].map((step, i) => (
                  <li key={i} className="flex gap-3 items-start">
                    <span
                      className="w-4 h-4 rounded flex items-center justify-center text-xs flex-shrink-0 mt-0.5"
                      style={{ background: 'var(--color-accent-dim)', color: 'var(--color-accent)', fontFamily: 'var(--font-mono)', fontSize: '0.65rem', fontWeight: 600 }}
                    >
                      {i + 1}
                    </span>
                    <span className="text-xs leading-relaxed" style={{ color: 'var(--color-muted)' }}>{step}</span>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </div>
      </main>
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
