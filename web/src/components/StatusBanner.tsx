import type { OrderRequestSource, Outcome } from '../types'

interface StatusBannerProps {
  outcome: Outcome | null
  message: string
  loading: boolean
  loadingKind?: 'preview' | 'submit' | null
  error: string | null
  previewSource?: OrderRequestSource | null
}

export function StatusBanner({
  outcome,
  message,
  loading,
  loadingKind = null,
  error,
  previewSource = null,
}: StatusBannerProps) {
  if (loading) {
    const text =
      loadingKind === 'submit'
        ? 'Submitting Order Create and waiting for response…'
        : 'Searching Datadog and preparing Order Create v6 request…'
    return (
      <div className="status-banner status-loading" role="status">
        {text}
      </div>
    )
  }
  if (error) {
    return (
      <div className="status-banner status-error" role="alert">
        {error}
      </div>
    )
  }
  if (!message) return null
  if (!outcome) {
    return (
      <div className="status-banner status-warn" role="status">
        {message}
      </div>
    )
  }

  const kind =
    outcome === 'SUCCESS' || outcome === 'READY'
      ? 'status-success'
      : outcome === 'FAILED'
        ? 'status-failed'
        : 'status-warn'

  return (
    <div className={`status-banner ${kind}`} role="status">
      {message}
      {outcome === 'READY' && previewSource ? (
        <span className="status-source">
          {' '}
          Source: {previewSource === 'v2-converted' ? 'converted from v2' : 'native v6'}
        </span>
      ) : null}
    </div>
  )
}
