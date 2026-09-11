interface PageHeaderProps {
  badge: string
  title?: string
  subtitle: string
}

export function PageHeader({ badge, title, subtitle }: PageHeaderProps) {
  return (
    <header className="page-hero">
      <span className="page-badge">{badge}</span>
      {title ? (
        <h1 className="page-title">{title}</h1>
      ) : (
        <h1 className="sr-only">{badge}</h1>
      )}
      <p className={title ? 'page-subtitle' : 'page-subtitle page-subtitle-after-badge'}>
        {subtitle}
      </p>
    </header>
  )
}
