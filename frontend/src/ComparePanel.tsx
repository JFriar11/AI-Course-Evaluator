import { useState } from 'react'
import { compareRuns, type Comparison } from './api'

/**
 * A second model's opinion is the cheapest honesty check we have: two models
 * that disagree on a criterion is a signal a human should read that criterion.
 * This panel compares two saved runs of the same report.
 */
export default function ComparePanel({ stems }: { stems: string[] }) {
  const [runA, setRunA] = useState(stems[0] ?? '')
  const [runB, setRunB] = useState(stems[1] ?? '')
  const [comparison, setComparison] = useState<Comparison | null>(null)
  const [error, setError] = useState('')

  if (stems.length < 2) return null

  const run = () => {
    setError('')
    compareRuns(runA, runB)
      .then(setComparison)
      .catch((exc) => { setComparison(null); setError(exc.message) })
  }

  const selectStyle = {
    background: 'var(--color-surface-2)',
    color: 'var(--color-text)',
    border: '1px solid var(--color-border)',
    'border-radius': 8,
    padding: '6px 10px',
    font: 'inherit',
    'font-family': 'var(--font-mono)',
    'font-size': 12,
  }

  return (
    <div className="rounded-xl p-5" style={{ border: '1px solid var(--color-border)', background: 'var(--color-surface)' }}>
      <div className="flex items-center gap-2 mb-3">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 3h18M3 21h18M12 3v18" />
        </svg>
        <span className="text-xs font-semibold" style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-muted)' }}>
          SECOND OPINION
        </span>
        <span className="ml-auto text-xs" style={{ color: 'var(--color-label)', fontFamily: 'var(--font-mono)' }}>
          compare two runs of the same report
        </span>
      </div>

      <div className="flex flex-wrap gap-2 items-center">
        <select value={runA} onChange={(e) => setRunA(e.target.value)} style={selectStyle}>
          {stems.map((stem) => <option key={stem} value={stem}>{stem}</option>)}
        </select>
        <span className="text-xs" style={{ color: 'var(--color-muted)', fontFamily: 'var(--font-mono)' }}>vs</span>
        <select value={runB} onChange={(e) => setRunB(e.target.value)} style={selectStyle}>
          {stems.map((stem) => <option key={stem} value={stem}>{stem}</option>)}
        </select>
        <button type="button" onClick={run}
          style={{ background: 'var(--color-accent)', color: 'var(--color-surface)', border: 'none', borderRadius: 8, padding: '6px 12px', font: 'inherit', fontSize: 12, cursor: 'pointer' }}>
          Compare
        </button>
      </div>

      {error && <p className="text-xs mt-3" style={{ color: 'var(--color-danger)' }}>{error}</p>}

      {comparison && (
        <div className="mt-4">
          <p className="text-sm" style={{ color: 'var(--color-text)' }}>
            The two runs agreed on {comparison.agreements} of {comparison.criteria_compared} criteria
            ({comparison.agreement_rate}%). Totals: {comparison.total_a} vs {comparison.total_b}
            {' — '}a difference of {comparison.total_difference} points.
          </p>

          <p className="text-xs mt-2" style={{ color: 'var(--color-muted)', fontFamily: 'var(--font-mono)' }}>
            Consensus score: {comparison.consensus?.score ?? 0}
            {' — '}{comparison.consensus?.needs_human_review ?? 0} criterion(s) that only a person can settle.
          </p>

          {comparison.disagreements.length === 0 ? (
            <p className="text-xs mt-2" style={{ color: 'var(--color-success)', fontFamily: 'var(--font-mono)' }}>
              No disagreements — the score is stable across models.
            </p>
          ) : (
            <div className="flex flex-col gap-2 mt-3">
              {comparison.disagreements.map((entry) => (
                <div key={entry.id} className="rounded p-3" style={{ background: 'var(--color-surface-2)', border: '1px solid var(--color-border)' }}>
                  <p className="text-sm" style={{ color: 'var(--color-text)' }}>
                    <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-muted)' }}>{entry.id}</span>
                    {entry.score_a > entry.score_b
                      ? ` — run A gave ${entry.score_a}, run B gave ${entry.score_b}`
                      : ` — run B gave ${entry.score_b}, run A gave ${entry.score_a}`}
                  </p>
                  <div className="flex flex-col gap-1 mt-2">
                    <p className="text-xs" style={{ color: 'var(--color-muted)' }}>
                      A ({entry.score_a}): {entry.evidence_a ? `“${entry.evidence_a}”` : 'no quote'}
                      {!entry.verified_a && <span style={{ color: 'var(--color-danger)', fontFamily: 'var(--font-mono)' }}> · quote not in report</span>}
                    </p>
                    <p className="text-xs" style={{ color: 'var(--color-muted)' }}>
                      B ({entry.score_b}): {entry.evidence_b ? `“${entry.evidence_b}”` : 'no quote'}
                      {!entry.verified_b && <span style={{ color: 'var(--color-danger)', fontFamily: 'var(--font-mono)' }}> · quote not in report</span>}
                    </p>
                  </div>
                  <p className="text-xs mt-2" style={{ color: 'var(--color-warning)', fontFamily: 'var(--font-mono)' }}>
                    {entry.supported_by
                      ? `Only ${entry.supported_by}'s quote can be traced to the report.`
                      : 'Neither quote can be traced — decide from the source document.'}
                    {' '}A human should read this criterion before the score is final.
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
