interface MetricCardsProps {
  runs: number
  success: number
  failed: number
  impulseOrder: string
}

export function MetricCards({ runs, success, failed, impulseOrder }: MetricCardsProps) {
  return (
    <div className="metric-cards">
      <div className="metric-card">
        <div className="metric-label">Runs</div>
        <div className="metric-value">{runs}</div>
      </div>
      <div className="metric-card">
        <div className="metric-label">Success</div>
        <div className="metric-value">{success}</div>
      </div>
      <div className="metric-card">
        <div className="metric-label">Failed</div>
        <div className="metric-value">{failed}</div>
      </div>
      <div className="metric-card">
        <div className="metric-label">Impulse Order</div>
        <div className="metric-value metric-value-text">{impulseOrder || '—'}</div>
      </div>
    </div>
  )
}
