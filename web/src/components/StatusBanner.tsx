import type { OrderRequestSource, Outcome } from '../types'

interface StatusBannerProps {
  outcome: Outcome | null
  message: string
  loading: boolean
  loadingKind?: 'preview' | 'submit' | null
  error: string | null
  previewSource?: OrderRequestSource | null
}

const RATE_LIMIT_TIPS = [
  'Wait 1–2 minutes and try again (Datadog rate limits are usually temporary).',
  'Run one curl type at a time (uncheck one checkbox) to cut API calls in half.',
  'Narrow the date range to the day you expect the order.',
  'Avoid clicking RUN many times in quick succession.',
  "If this keeps happening often, check your Datadog org's API limits or use a token/key with higher quota.",
]

function isRateLimitError(error: string): boolean {
  return /rate limit exceeded/i.test(error)
}

export function StatusBanner({
  outcome,
  message,
  loading,
  loadingKind = null,
  error,
  previewSource = null,
}: StatusBannerProps) {
  const displayError =
    error ??
    (import.meta.env.DEV &&
    typeof window !== 'undefined' &&
    new URLSearchParams(window.location.search).has('rateLimitDemo')
      ? 'Datadog fetch failed: Rate limit exceeded'
      : null)

  if (loading) {
    const text =
      loadingKind === 'submit'
        ? 'Submitting Order Create and waiting for response…'
        : 'Searching DataDog and preparing request curl..'
    return (
      <div className="status-banner status-loading" role="status">
        {text}
      </div>
    )
  }
  if (displayError) {
    if (isRateLimitError(displayError)) {
      return (
        <div className="status-banner status-error status-error-rate-limit" role="alert">
          <span className="status-error-rate-limit-trigger" tabIndex={0}>
            {displayError}
          </span>
          <div className="status-error-rate-limit-popover" role="tooltip">
            <p className="status-error-rate-limit-popover-title">What to do</p>
            <ul className="status-error-rate-limit-popover-list">
              {RATE_LIMIT_TIPS.map((tip) => (
                <li key={tip}>{tip}</li>
              ))}
            </ul>
          </div>
        </div>
      )
    }
    return (
      <div className="status-banner status-error" role="alert">
        {displayError}
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
