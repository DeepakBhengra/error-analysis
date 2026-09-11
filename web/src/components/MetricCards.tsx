interface MetricCardsProps {
  runs: number
  success: number
  failed: number
  impulseOrder: string
}

function MetricIcon({ type }: { type: 'runs' | 'success' | 'failed' | 'order' }) {
  const paths: Record<typeof type, string> = {
    runs: 'M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-5 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z',
    success:
      'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z',
    failed:
      'M12 2C6.47 2 2 6.47 2 12s4.47 10 10 10 10-4.47 10-10S17.53 2 12 2zm5 13.59L15.59 17 12 13.41 8.41 17 7 15.59 10.59 12 7 8.41 8.41 7 12 10.59 15.59 7 17 8.41 13.41 12 17 15.59z',
    order:
      'M7 18c-1.1 0-1.99.9-1.99 2S5.9 22 7 22s2-.9 2-2-.9-2-2-2zM1 2v2h2l3.6 7.59-1.35 2.45c-.16.28-.25.61-.25.96 0 1.1.9 2 2 2h12v-2H7.42c-.14 0-.25-.11-.25-.25l.03-.12.9-1.63h7.45c.75 0 1.41-.41 1.75-1.03l3.58-6.49A1.003 1.003 0 0 0 20 4H5.21l-.94-2H1zm16 16c-1.1 0-1.99.9-1.99 2s.89 2 1.99 2 2-.9 2-2-.9-2-2-2z',
  }
  return (
    <span className="metric-icon" aria-hidden>
      <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
        <path d={paths[type]} />
      </svg>
    </span>
  )
}

export function MetricCards({ runs, success, failed, impulseOrder }: MetricCardsProps) {
  const items = [
    { key: 'runs', label: 'Runs', value: String(runs), icon: 'runs' as const },
    { key: 'success', label: 'Success', value: String(success), icon: 'success' as const },
    { key: 'failed', label: 'Failed', value: String(failed), icon: 'failed' as const },
    {
      key: 'impulse',
      label: 'Impulse Order',
      value: impulseOrder || '—',
      icon: 'order' as const,
      compact: Boolean(impulseOrder),
    },
  ]

  return (
    <section className="summary-strip" aria-label="Session summary">
      {items.map((item) => (
        <div key={item.key} className="summary-metric">
          <MetricIcon type={item.icon} />
          <div className="summary-metric-body">
            <span className="summary-metric-label">{item.label}</span>
            <span
              className={
                item.compact ? 'summary-metric-value summary-metric-value-sm' : 'summary-metric-value'
              }
            >
              {item.value}
            </span>
          </div>
        </div>
      ))}
    </section>
  )
}
