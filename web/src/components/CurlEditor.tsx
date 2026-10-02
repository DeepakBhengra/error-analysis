import { useMemo, useState } from 'react'

import { guessOrderTypeFromCurl } from '../guessOrderType'
import type { CurlHttpResponse, CurlPanelTab, OrrorhField } from '../types'
import { CopyButton } from './CopyButton'
import { Orrorh88Popup } from './Orrorh88Popup'

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
  substationLogs?: string
  substationFields?: OrrorhField[]
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

function resolveSubstationFields(
  fields: OrrorhField[],
  report: string,
): OrrorhField[] {
  if (fields.length) return fields
  const parsed: OrrorhField[] = []
  for (const line of report.split('\n')) {
    const match = line.match(/^\d+\.\s+(ORRORH-[A-Z0-9-]+)\s+=\s+(.*)$/)
    if (match) parsed.push({ name: match[1], value: match[2] })
  }
  return parsed
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
  substationLogs = '',
  substationFields = [],
  onCreateChange,
  onModifyChange,
  onResubmit,
  onCancel,
}: CurlEditorProps) {
  const [conditionField, setConditionField] = useState<OrrorhField | null>(null)
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
  const resolvedFields = useMemo(
    () => resolveSubstationFields(substationFields, substationLogs),
    [substationFields, substationLogs],
  )

  const panelTitle = activeTab === 'modify' ? 'Order Modify Curl' : 'Order Create Curl'

  return (
    <section className="curl-panel page-card">
      <div className="detail-tabs" role="tablist" aria-label="Curl type">
        {showCreateTab ? (
          <button
            type="button"
            className={`detail-tab${activeTab === 'create' ? ' active' : ''}`}
            onClick={() => onTabChange('create')}
          >
            Order Create curl
          </button>
        ) : null}
        {showModifyTab ? (
          <button
            type="button"
            className={`detail-tab${activeTab === 'modify' ? ' active' : ''}`}
            onClick={() => onTabChange('modify')}
          >
            Order Modify curl
          </button>
        ) : null}
      </div>
      <div className="detail-section-header">
        <div className="detail-section-title-wrap">
          <span className="detail-section-icon" aria-hidden>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
              <path d="M9.4 16.6 4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0 4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z" />
            </svg>
          </span>
          <div>
            <h2 className="detail-section-title">{panelTitle}</h2>
            <p className="detail-section-meta">Request curl editor</p>
          </div>
        </div>
        <div className="curl-panel-actions">
          <button
            type="button"
            className="btn-primary"
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
          : 'RUN prepares a v6 Order Create curl (converting from v2 when needed) without posting. Edit below, then Re-Submit. One-up increments the customerOrderNumber currently in this curl; Random replaces it. Both stay at most 18 characters and also update endCustomerOrderNumber.'}
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
      <div className="copyable-panel">
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
        <CopyButton text={curl} label="Copy curl" />
      </div>
      {httpResponse ? (
        <div className="curl-response-panel">
          <div className="curl-response-header">
            <h3>Postman / API Response</h3>
            <div className="curl-response-header-actions">
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
          <div className="copyable-panel">
            <pre className="curl-response-body">
              {responseText || '(empty response body)'}
            </pre>
            <CopyButton text={responseText} label="Copy API response" />
          </div>
        </div>
      ) : null}
      {activeTab === 'create' && (createCurl.trim() || substationLogs.trim()) ? (
        <div className="curl-response-panel curl-substation-panel">
          <div className="curl-response-header">
            <h3>Substation Logs</h3>
          </div>
          <p className="curl-hint">
            ORRORH copybook fields from the OrderUpdate Substation Request for this
            customer PO. Empty tags are Spaces. ORRORD-DETAIL-ELEMENTS is ignored.
            Click a highlighted field to view its 88 condition-names.
          </p>
          <div className="copyable-panel">
            {substationLogs.trim() ? (
              <ol className="curl-response-body curl-orrorh-body orrorh-field-list">
                {resolvedFields.map((field, index) => {
                  const clickable = Boolean(
                    field.conditions?.length && field.value.trim() && field.value !== 'Spaces',
                  )
                  return (
                    <li key={`${index}-${field.name}`} className="orrorh-field-row">
                      <span className="orrorh-field-index">{index + 1}.</span>
                      {clickable ? (
                        <button
                          type="button"
                          className="orrorh-field-link"
                          onClick={() => setConditionField(field)}
                        >
                          {field.name}
                        </button>
                      ) : (
                        <span className="orrorh-field-name">{field.name}</span>
                      )}
                      <span className="orrorh-field-eq"> = </span>
                      <span className="orrorh-field-value">{field.value}</span>
                    </li>
                  )
                })}
              </ol>
            ) : (
              <pre className="curl-response-body curl-orrorh-body">
                No Substation Request found for this customer PO.
              </pre>
            )}
            <CopyButton
              text={substationLogs}
              label="Copy Substation Logs"
            />
          </div>
          <Orrorh88Popup field={conditionField} onClose={() => setConditionField(null)} />
        </div>
      ) : null}
    </section>
  )
}
