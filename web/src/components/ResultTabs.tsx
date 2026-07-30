import type { TabFilter } from '../types'

interface ResultTabsProps {
  tab: TabFilter
  allCount: number
  successCount: number
  failedCount: number
  onChange: (tab: TabFilter) => void
}

export function ResultTabs({
  tab,
  allCount,
  successCount,
  failedCount,
  onChange,
}: ResultTabsProps) {
  return (
    <div className="result-tabs" role="tablist">
      <button
        type="button"
        role="tab"
        aria-selected={tab === 'all'}
        className={tab === 'all' ? 'tab active' : 'tab'}
        onClick={() => onChange('all')}
      >
        All Results <span className="tab-badge">{allCount}</span>
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={tab === 'success'}
        className={tab === 'success' ? 'tab active' : 'tab'}
        onClick={() => onChange('success')}
      >
        Success <span className="tab-badge">{successCount}</span>
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={tab === 'failed'}
        className={tab === 'failed' ? 'tab active' : 'tab'}
        onClick={() => onChange('failed')}
      >
        Failed <span className="tab-badge">{failedCount}</span>
      </button>
    </div>
  )
}
