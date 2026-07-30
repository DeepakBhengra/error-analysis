import type { ReactNode } from 'react'

export type AppView = 'home' | 'settings'

interface AppShellProps {
  children: ReactNode
  view: AppView
  onNavigate: (view: AppView) => void
}

export function AppShell({ children, view, onNavigate }: AppShellProps) {
  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Main navigation">
        <button
          type="button"
          className={`sidebar-icon${view === 'home' ? ' active' : ''}`}
          title="Home"
          aria-label="Home"
          aria-current={view === 'home' ? 'page' : undefined}
          onClick={() => onNavigate('home')}
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden>
            <path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z" />
          </svg>
        </button>
        <button
          type="button"
          className={`sidebar-icon${view === 'settings' ? ' active' : ''}`}
          title="Settings"
          aria-label="Settings"
          aria-current={view === 'settings' ? 'page' : undefined}
          onClick={() => onNavigate('settings')}
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden>
            <path d="M19.14 12.94c.04-.31.06-.63.06-.94s-.02-.63-.06-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.49.49 0 0 0-.59-.22l-2.39.96a7.2 7.2 0 0 0-1.63-.94l-.36-2.54A.49.49 0 0 0 13.95 2h-3.9a.49.49 0 0 0-.48.41l-.36 2.54c-.59.24-1.13.55-1.63.94l-2.39-.96a.49.49 0 0 0-.59.22L2.68 8.47a.49.49 0 0 0 .12.61l2.03 1.58c-.04.31-.06.63-.06.94s.02.63.06.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.13.23.4.32.64.22l2.39-.96c.5.39 1.04.7 1.63.94l.36 2.54c.05.24.25.41.48.41h3.9c.23 0 .43-.17.48-.41l.36-2.54c.59-.24 1.13-.55 1.63-.94l2.39.96c.24.1.51 0 .64-.22l1.92-3.32a.49.49 0 0 0-.12-.61l-2.03-1.58zM12 15.5A3.5 3.5 0 1 1 12 8.5a3.5 3.5 0 0 1 0 7z" />
          </svg>
        </button>
      </aside>
      <main className="main-content">{children}</main>
    </div>
  )
}
