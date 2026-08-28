import type { FormEvent } from 'react'

import type { CurlType } from '../types'

interface SearchBarProps {
  query: string
  from: string
  to: string
  curlTypes: CurlType[]
  loading: boolean
  canCancel?: boolean
  onQueryChange: (value: string) => void
  onFromChange: (value: string) => void
  onToChange: (value: string) => void
  onCurlTypesChange: (value: CurlType[]) => void
  onRun: () => void
  onCancel?: () => void
  onRefresh: () => void
}

const CURL_TYPE_OPTIONS: { value: CurlType; label: string }[] = [
  { value: 'create', label: 'Order Create curl' },
  { value: 'modify', label: 'Order Modify curl' },
]

export function SearchBar({
  query,
  from,
  to,
  curlTypes,
  loading,
  canCancel = false,
  onQueryChange,
  onFromChange,
  onToChange,
  onCurlTypesChange,
  onRun,
  onCancel,
  onRefresh,
}: SearchBarProps) {
  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    onRun()
  }

  const toggleCurlType = (type: CurlType) => {
    if (curlTypes.includes(type)) {
      const next = curlTypes.filter((item) => item !== type)
      onCurlTypesChange(next.length ? next : [type])
      return
    }
    onCurlTypesChange([...curlTypes, type])
  }

  return (
    <form className="search-section" onSubmit={handleSubmit}>
      <fieldset className="curl-type-fieldset" disabled={loading}>
        <legend className="sr-only">Curl types to build</legend>
        {CURL_TYPE_OPTIONS.map((option) => (
          <label key={option.value} className="curl-type-option">
            <input
              type="checkbox"
              checked={curlTypes.includes(option.value)}
              onChange={() => toggleCurlType(option.value)}
            />
            {option.label}
          </label>
        ))}
      </fieldset>
      <div className="search-row">
        <div className="search-input-wrap">
          <svg
            className="search-icon"
            viewBox="0 0 24 24"
            width="18"
            height="18"
            fill="currentColor"
            aria-hidden
          >
            <path d="M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z" />
          </svg>
          <input
            type="text"
            className="search-input"
            placeholder="Customer order number (e.g. DEEPAKDDTEST12)"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            disabled={loading}
            aria-label="Search Datadog logs by customer order number"
          />
        </div>
        <button
          type="submit"
          className="btn-outline-primary"
          disabled={loading || !query.trim() || !curlTypes.length}
        >
          RUN
        </button>
        {canCancel ? (
          <button type="button" className="btn-outline-cancel" onClick={onCancel}>
            Cancel
          </button>
        ) : null}
        <button
          type="button"
          className="btn-icon"
          onClick={onRefresh}
          disabled={loading}
          title="Refresh"
          aria-label="Refresh"
        >
          <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden>
            <path d="M17.65 6.35A7.95 7.95 0 0 0 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0 1 12 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z" />
          </svg>
        </button>
      </div>
      <div className="controls-row">
        <label className="control-field">
          <span>From</span>
          <input
            type="datetime-local"
            value={from}
            onChange={(e) => onFromChange(e.target.value)}
            disabled={loading}
          />
        </label>
        <label className="control-field">
          <span>To</span>
          <input
            type="datetime-local"
            value={to}
            onChange={(e) => onToChange(e.target.value)}
            disabled={loading}
          />
        </label>
      </div>
    </form>
  )
}
