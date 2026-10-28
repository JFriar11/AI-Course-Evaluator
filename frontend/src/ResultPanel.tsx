import { Job, JobResult, SectionSummary, downloadUrl, savedDownloadUrl } from './api'

function scoreColor(score: number) {
  if (score >= 1) return 'var(--color-success)'
  if (score >= 0.5) return 'var(--color-warning)'
  return 'var(--color-danger)'
}

function DownloadLink({ jobId, kind, label }: { jobId: string; kind: string; label: string }) {
  // Reports opened from Output/ have no job record, only files on disk.
  const href = jobId.startsWith('file:')
    ? savedDownloadUrl(jobId.slice('file:'.length), kind)
    : downloadUrl(jobId, kind)
  return (
    <a
      href={href}
      className="text-xs px-2.5 py-1.5 rounded-lg font-medium transition-opacity hover:opacity-80"
      style={{
        background: 'var(--color-surface-2)',
        color: 'var(--color-text)',
        border: '1px solid var(--color-border)',
        fontFamily: 'var(--font-mono)',
        textDecoration: 'none',
      }}
    >
      {label}
    </a>
  )
}

export default function ResultPanel({ job }: { job: Job }) {
  const result: JobResult = job.result!
  const sections: SectionSummary[] = result.sections ?? []
  const total = Number(result.scorecard.total_calculated_score ?? 0)
  const summary = typeof result.detail.summary === 'string' ? result.detail.summary : ''
  const maxPoints = result.max_points || 23
  const unverified = result.unverified_evidence ?? 0
  const verifiedScore = Number(result.scorecard.verified_score ?? total)
  const percent = Math.round((total / maxPoints) * 100)

  return (
    <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--color-border)', background: 'var(--color-surface)' }}>
      <div className="px-5 py-4 flex items-center justify-between gap-4" style={{ borderBottom: '1px solid var(--color-border)' }}>
        <div className="min-w-0">
          <p className="text-sm font-medium truncate" style={{ color: 'var(--color-text)' }}>{job.filename}</p>
          <p className="text-xs mt-1" style={{ color: 'var(--color-muted)', fontFamily: 'var(--font-mono)' }}>
            {result.extraction.pages} pages · {result.extraction.ocr_pages} OCR · {result.extraction.characters.toLocaleString()} characters
          </p>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          <span className="text-2xl font-semibold" style={{ fontFamily: 'var(--font-display)', color: scoreColor(total / maxPoints) }}>
            {total}
          </span>
          <span className="text-xs" style={{ color: 'var(--color-muted)', fontFamily: 'var(--font-mono)' }}>
            / {maxPoints}
          </span>
          {verifiedScore < total && (
            <span className="text-xs" style={{ color: 'var(--color-muted)', fontFamily: 'var(--font-mono)' }}>
              ({verifiedScore} evidenced)
            </span>
          )}
        </div>
      </div>

      <div className="px-5 py-3">
        <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--color-surface-2)' }}>
          <div className="h-full rounded-full" style={{ width: `${percent}%`, background: 'var(--color-accent)' }} />
        </div>
      </div>

      {unverified > 0 && (
        <div className="px-5 py-2" style={{ background: 'var(--color-surface-2)', borderBottom: '1px solid var(--color-border)' }}>
          <p className="text-xs" style={{ color: 'var(--color-warning)', fontFamily: 'var(--font-mono)' }}>
            {unverified} evidence quote(s) could not be matched to the document text - check before submitting.
          </p>
        </div>
      )}

      {(result.missed_point_review ?? 0) > 0 && (
        <div className="rounded p-3 text-sm" style={{ background: 'var(--color-surface-2)', color: 'var(--color-warning)' }}>
          {result.missed_point_review} criterion(s) scored 0 with no quote, but the report contains
          passages matching their wording - a human should confirm these are genuinely absent.
        </div>
      )}
      {result.recheck?.attempted && (
        <div className="px-5 py-2" style={{ borderBottom: '1px solid var(--color-border)' }}>
          <p className="text-xs" style={{ color: 'var(--color-muted)', fontFamily: 'var(--font-mono)' }}>
            Second pass: the model was re-asked about {result.recheck.flagged} unsupported{' '}
            {result.recheck.flagged === 1 ? 'criterion' : 'criteria'} and revised {result.recheck.changed}.
          </p>
        </div>
      )}

      <div className="px-5 py-2">
        {sections.map((section) => (
          <div key={section.key} className="py-3" style={{ borderBottom: '1px solid var(--color-border)' }}>
            <div className="flex items-center justify-between gap-3 mb-2">
              <span className="text-xs font-semibold" style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-muted)' }}>
                {section.label.toUpperCase()}
              </span>
              <span className="text-xs" style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-text)' }}>
                {section.score} / {section.max}
              </span>
            </div>
            <div className="flex flex-col gap-2">
              {section.criteria.map((criterion) => (
                <div key={criterion.id} className="flex gap-3 items-start">
                  <span
                    className="w-11 h-6 rounded flex items-center justify-center text-xs font-bold flex-shrink-0"
                    style={{ background: 'var(--color-surface-2)', color: scoreColor(criterion.score), fontFamily: 'var(--font-mono)' }}
                  >
                    {criterion.score}
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm" style={{ color: 'var(--color-text)' }}>
                      <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-muted)' }}>{criterion.id}</span>
                      {criterion.note
                        ? ` — ${criterion.note}`
                        : criterion.heading
                          ? ` — ${criterion.heading}`
                          : ''}
                    </p>
                    {criterion.evidence && (
                      <p className="text-xs mt-1" style={{ color: 'var(--color-muted)' }}>
                        “{criterion.evidence}”
                        {criterion.evidence_verified === false && (
                          <span style={{ color: 'var(--color-danger)', fontFamily: 'var(--font-mono)' }}>
                            {' '}· {criterion.evidence_source === 'rubric'
                              ? 'the rubric wording, not the report'
                              : criterion.evidence_source === 'script_fact'
                                ? 'the automated pre-check, not the report'
                                : 'not found in the report'}
                          </span>
                        )}
                      </p>
                    )}
                    {criterion.possible_missed_point && (
                      <p className="text-xs mt-1" style={{ color: 'var(--color-warning)' }}>
                        Scored 0, but the report appears to address this - the AI may have missed it.
                        Check: <span style={{ fontFamily: 'var(--font-mono)' }}>{criterion.review_hint}</span>
                      </p>
                    )}
                    {criterion.evidence_verified === false && criterion.review_hint && (
                      <p className="text-xs mt-1" style={{ color: 'var(--color-muted)' }}>
                        Search the report for: <span style={{ fontFamily: 'var(--font-mono)' }}>{criterion.review_hint}</span>
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {summary && (
        <div className="px-5 py-3" style={{ borderBottom: '1px solid var(--color-border)' }}>
          <p className="text-xs font-semibold mb-2" style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-muted)' }}>
            SUMMARY
          </p>
          <p className="text-sm leading-relaxed" style={{ color: 'var(--color-text)' }}>{summary}</p>
        </div>
      )}

      <div className="px-5 py-4 flex flex-wrap gap-2">
        <DownloadLink jobId={job.id} kind="scorecard" label="scorecard.json" />
        <DownloadLink jobId={job.id} kind="feedback" label="feedback.md" />
        <DownloadLink jobId={job.id} kind="detail" label="full detail" />
        <DownloadLink jobId={job.id} kind="audit_trail" label="audit trail" />
        <DownloadLink jobId={job.id} kind="extracted_text" label="extracted text" />
      </div>
    </div>
  )
}
