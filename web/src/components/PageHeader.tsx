interface PageHeaderProps {
  badge: string
  title: string
  subtitle: string
}

export function PageHeader({ badge, title, subtitle }: PageHeaderProps) {
  return (
    <header className="page-hero">
      <span className="page-badge">{badge}</span>
      <h1 className="page-title">{title}</h1>
      <p className="page-subtitle">{subtitle}</p>
    </header>
  )
}
