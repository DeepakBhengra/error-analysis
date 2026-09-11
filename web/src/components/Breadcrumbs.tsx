import type { AppView } from './AppShell'

interface BreadcrumbsProps {
  timestamp: string
  view?: AppView
}

export function Breadcrumbs({ timestamp, view = 'home' }: BreadcrumbsProps) {
  return (
    <div className="top-bar">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <span className="crumb">Home</span>
        <span className="crumb-sep" aria-hidden>
          /
        </span>
        {view === 'settings' ? (
          <span className="crumb-current">Settings</span>
        ) : (
          <>
            <span className="crumb">Error Analysis</span>
            <span className="crumb-sep" aria-hidden>
              /
            </span>
            <span className="crumb-current">Order Replay</span>
          </>
        )}
      </nav>
      <time className="header-meta" dateTime={timestamp}>
        {timestamp}
      </time>
    </div>
  )
}
