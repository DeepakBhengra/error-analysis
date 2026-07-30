import type { AppView } from './AppShell'

interface BreadcrumbsProps {
  timestamp: string
  view?: AppView
}

export function Breadcrumbs({ timestamp, view = 'home' }: BreadcrumbsProps) {
  return (
    <div className="page-header">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <span>Home</span>
        <span className="crumb-sep">&gt;</span>
        {view === 'settings' ? (
          <span className="crumb-current">Settings</span>
        ) : (
          <>
            <span>Error Analysis</span>
            <span className="crumb-sep">&gt;</span>
            <span className="crumb-current">Order Replay</span>
          </>
        )}
      </nav>
      <div className="header-meta">{timestamp}</div>
    </div>
  )
}
