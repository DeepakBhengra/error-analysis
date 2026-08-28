import { useMemo } from 'react'

import { guessOrderTypeFromCurl } from '../guessOrderType'
import type { CurlHttpResponse, CurlPanelTab } from '../types'

interface CurlEditorProps {
  activeTab: CurlPanelTab
  onTabChange: (tab: CurlPanelTab) => void
  showCreateTab: boolean
  showModifyTab: boolean
  createCurl: string
  modifyCurl: string
  loading: boolean
  canCancel?: boolean
  httpResponse?: CurlHttpResponse | null
  onCreateChange: (value: string) => void
  onModifyChange: (value: string) => void
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
  activeTab,
  onTabChange,
  showCreateTab,
  showModifyTab,
  createCurl,
  modifyCurl,
  loading,
  canCancel = false,
  httpResponse = null,
  onCreateChange,
  onModifyChange,
  onResubmit,
  onCancel,
}: CurlEditorProps) {
  const curl = activeTab === 'modify' ? modifyCurl : createCurl
  const onChange = activeTab === 'modify' ? onModifyChange : onCreateChange

  const responseText =
    httpResponse && httpResponse.httpBody !== undefined && httpResponse.httpBody !== null
      ? formatHttpBody(httpResponse.httpBody)
      : ''

  const orderTypeHint = useMemo(
    () => (activeTab === 'create' ? guessOrderTypeFromCurl(createCurl) : null),
    [activeTab, createCurl],
  )

  const panelTitle = activeTab === 'modify' ? 'Order Modify Curl' : 'Order Create Curl'

  return (
    <section className="curl-panel">
      <div className="curl-panel-tabs">
        {showCreateTab ? (
          <button
            type="button"
            className={`curl-panel-tab${activeTab === 'create' ? ' active' : ''}`}
            onClick={() => onTabChange('create')}
          >
            Order Create curl
          </button>
        ) : null}
        {showModifyTab ? (
          <button
            type="button"
            className={`curl-panel-tab${activeTab === 'modify' ? ' active' : ''}`}
            onClick={() => onTabChange('modify')}
          >
            Order Modify curl
          </button>
        ) : null}
      </div>
      <div className="curl-panel-header">
        <h2>{panelTitle}</h2>
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
        {activeTab === 'modify'
          ? 'RUN prepares a PUT Order Modify curl from Datadog RequestPayload without posting. Edit below, then Re-Submit.'
          : 'RUN prepares a v6 Order Create curl (converting from v2 when needed) without posting. Edit below, then Re-Submit. One-up or random is applied to customerOrderNumber only on Re-Submit.'}
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
        placeholder={
          activeTab === 'modify'
            ? 'Order Modify curl will appear here after RUN…'
            : 'Curl will appear here after RUN prepares a v6 request…'
        }
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
