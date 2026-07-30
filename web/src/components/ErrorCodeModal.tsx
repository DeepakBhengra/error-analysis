import type { ErrorLookupResponse } from '../types'

interface ErrorCodeModalProps {
  open: boolean
  errorCode: string
  loading: boolean
  error: string | null
  result: ErrorLookupResponse | null
  onClose: () => void
}

export function ErrorCodeModal({
  open,
  errorCode,
  loading,
  error,
  result,
  onClose,
}: ErrorCodeModalProps) {
  if (!open) return null

  return (
    <div className="modal-overlay" onClick={onClose} role="presentation">
      <div
        className="modal-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="error-lookup-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h2 id="error-lookup-title">Error Code Description</h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <div className="modal-body">
          {loading ? (
            <p className="modal-status">Looking up error code {errorCode}…</p>
          ) : error ? (
            <p className="modal-error">{error}</p>
          ) : result ? (
            <dl className="lookup-details">
              <div className="lookup-row">
                <dt>Error Code</dt>
                <dd>{result.error_code || errorCode}</dd>
              </div>
              <div className="lookup-row">
                <dt>Error Field</dt>
                <dd>{result.error_field || '—'}</dd>
              </div>
              <div className="lookup-row lookup-row-block">
                <dt>Historical Resolution</dt>
                <dd className="lookup-resolution">
                  {result.historical_resolution || 'No historical resolution available.'}
                </dd>
              </div>
            </dl>
          ) : (
            <p className="modal-status">No lookup data available.</p>
          )}
        </div>
      </div>
    </div>
  )
}
