import { useMemo } from 'react'

import { guessOrderTypeFromCurl } from '../guessOrderType'
import type { CurlHttpResponse } from '../types'

interface CurlEditorProps {
  curl: string
  loading: boolean
  canCancel?: boolean
  httpResponse?: CurlHttpResponse | null
  onChange: (value: string) => void
  onResubmit: () => void
  onCancel?: () => void
}

function formatHttpBody(body: unknown): string {
  if (body == null) return ''
  if (typeof body === 'string') {
    try {
      return JSON.stringify(JSON.parse(body), null, 2)
    } catch {
      return body
    }
  }
  try {
    return JSON.stringify(body, null, 2)
  } catch {
    return String(body)
  }
}

export function CurlEditor({
  curl,
  loading,
  canCancel = false,
  httpResponse = null,
  onChange,
  onResubmit,
  onCancel,
}: CurlEditorProps) {
  const responseText =
    httpResponse && httpResponse.httpBody !== undefined && httpResponse.httpBody !== null
      ? formatHttpBody(httpResponse.httpBody)
      : ''

  const orderTypeHint = useMemo(() => guessOrderTypeFromCurl(curl), [curl])

  return (
    <section className="curl-panel">
      <div className="curl-panel-header">
        <h2>Order Create Curl</h2>
        <div className="curl-panel-actions">
          <button
            type="button"
            className="btn-outline-primary"
            onClick={onResubmit}
            disabled={loading || !curl.trim()}
          >
            Re-Submit
          </button>
          {canCancel ? (
            <button type="button" className="btn-outline-cancel" onClick={onCancel}>
              Cancel
            </button>
          ) : null}
        </div>
      </div>
      <p className="curl-hint">
        RUN prepares a v6 Order Create curl (converting from v2 when needed) without posting.
        Edit below, then Re-Submit. One-up or random is applied to customerOrderNumber only on
        Re-Submit.
      </p>
      {orderTypeHint ? (
        <div
          className={`curl-order-type-note curl-order-type-note-${orderTypeHint.guess.toLowerCase()}`}
          title={orderTypeHint.detail}
        >
          <div className="curl-order-type-row">
            <span className="curl-order-type-label">{orderTypeHint.label}</span>
            <span className="curl-order-type-scores">
              D {orderTypeHint.dScore}
              <span className="curl-order-type-scores-sep">·</span>
              S {orderTypeHint.sScore}
            </span>
          </div>
          <p className="curl-order-type-detail">{orderTypeHint.detail}</p>
          {(orderTypeHint.dSignals.length > 0 || orderTypeHint.sSignals.length > 0) && (
            <div className="curl-order-type-signals">
              {orderTypeHint.dSignals.slice(0, 8).map((signal) => (
                <span key={`d-${signal}`} className="curl-order-type-chip curl-order-type-chip-d">
                  {signal}
                </span>
              ))}
              {orderTypeHint.sSignals.slice(0, 8).map((signal) => (
                <span key={`s-${signal}`} className="curl-order-type-chip curl-order-type-chip-s">
                  {signal}
                </span>
              ))}
            </div>
          )}
        </div>
      ) : null}
      <textarea
        className="curl-textarea"
        value={curl}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
        disabled={loading}
        placeholder="Curl will appear here after RUN prepares a v6 request…"
        rows={16}
      />
      {httpResponse ? (
        <div className="curl-response-panel">
          <div className="curl-response-header">
            <h3>Postman / API Response</h3>
            {httpResponse.httpStatus != null ? (
              <span
                className={
                  httpResponse.httpStatus >= 400
                    ? 'curl-response-status curl-response-status-error'
                    : 'curl-response-status curl-response-status-ok'
                }
              >
                HTTP {httpResponse.httpStatus}
              </span>
            ) : (
              <span className="curl-response-status">No HTTP status</span>
            )}
          </div>
          {httpResponse.curlRepaired ? (
            <p className="curl-repair-note">
              Curl was repaired
              {httpResponse.repairedFields.length
                ? `: added ${httpResponse.repairedFields.join(', ')}`
                : ''}
              . Review above and click Re-Submit again.
            </p>
          ) : null}
          {httpResponse.unresolvedFields.length ? (
            <p className="curl-repair-note curl-repair-note-warn">
              Cannot safely infer: {httpResponse.unresolvedFields.join(', ')}. Edit the curl
              manually.
            </p>
          ) : null}
          {httpResponse.repairMessage &&
          !httpResponse.curlRepaired &&
          !httpResponse.unresolvedFields.length ? (
            <p className="curl-repair-note">{httpResponse.repairMessage}</p>
          ) : null}
          <pre className="curl-response-body">
            {responseText || '(empty response body)'}
          </pre>
        </div>
      ) : null}
    </section>
  )
}
