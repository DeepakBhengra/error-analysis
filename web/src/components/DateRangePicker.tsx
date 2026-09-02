import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'

interface DateRangePickerProps {
  from: string
  to: string
  disabled?: boolean
  onFromChange: (value: string) => void
  onToChange: (value: string) => void
}

type Phase = 'idle' | 'picking-end'

function parseLocalDatetime(value: string): Date | null {
  if (!value) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d
}

function formatLocalDatetime(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  )
}

function mergeDateWithTime(date: Date, timeSource: string): string {
  const source = parseLocalDatetime(timeSource)
  const merged = new Date(date)
  merged.setHours(source?.getHours() ?? 0, source?.getMinutes() ?? 0, 0, 0)
  return formatLocalDatetime(merged)
}

function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate())
}

function sameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  )
}

function formatDisplay(value: string): string {
  const d = parseLocalDatetime(value)
  if (!d) return '—'
  return d.toLocaleString(undefined, {
    month: '2-digit',
    day: '2-digit',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function monthLabel(year: number, month: number): string {
  return new Date(year, month, 1).toLocaleString(undefined, {
    month: 'long',
    year: 'numeric',
  })
}

function buildMonthGrid(year: number, month: number): (Date | null)[] {
  const first = new Date(year, month, 1)
  const startOffset = first.getDay()
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const cells: (Date | null)[] = Array.from({ length: startOffset }, () => null)
  for (let day = 1; day <= daysInMonth; day += 1) {
    cells.push(new Date(year, month, day))
  }
  while (cells.length % 7 !== 0) cells.push(null)
  return cells
}

export function DateRangePicker({
  from,
  to,
  disabled = false,
  onFromChange,
  onToChange,
}: DateRangePickerProps) {
  const popoverId = useId()
  const rootRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [phase, setPhase] = useState<Phase>('idle')
  const [rangeStart, setRangeStart] = useState<Date | null>(null)

  const fromDate = parseLocalDatetime(from)
  const toDate = parseLocalDatetime(to)
  const anchor = fromDate ?? toDate ?? new Date()
  const [viewYear, setViewYear] = useState(anchor.getFullYear())
  const [viewMonth, setViewMonth] = useState(anchor.getMonth())

  useEffect(() => {
    if (!open) return
    const anchorDate = parseLocalDatetime(from) ?? parseLocalDatetime(to) ?? new Date()
    setViewYear(anchorDate.getFullYear())
    setViewMonth(anchorDate.getMonth())
    setPhase('idle')
    setRangeStart(null)
  }, [open, from, to])

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false)
        setPhase('idle')
        setRangeStart(null)
      }
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [open])

  const rangeEndPreview = phase === 'picking-end' ? rangeStart : null
  const effectiveStart = rangeStart ?? fromDate
  const effectiveEnd = phase === 'idle' ? toDate : rangeEndPreview

  const applyRange = (start: Date, end: Date) => {
    let startDay = startOfDay(start)
    let endDay = startOfDay(end)
    if (endDay < startDay) [startDay, endDay] = [endDay, startDay]
    onFromChange(mergeDateWithTime(startDay, from))
    onToChange(mergeDateWithTime(endDay, to))
    setOpen(false)
    setPhase('idle')
    setRangeStart(null)
  }

  const onDayClick = (day: Date) => {
    if (disabled) return
    if (phase === 'idle') {
      setRangeStart(startOfDay(day))
      setPhase('picking-end')
      return
    }
    if (rangeStart) {
      applyRange(rangeStart, day)
    }
  }

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === 'Escape') {
      setOpen(false)
      setPhase('idle')
      setRangeStart(null)
    }
  }

  const shiftMonth = (delta: number) => {
    const next = new Date(viewYear, viewMonth + delta, 1)
    setViewYear(next.getFullYear())
    setViewMonth(next.getMonth())
  }

  const cells = buildMonthGrid(viewYear, viewMonth)
  const weekdayLabels = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']

  const isInRange = (day: Date): boolean => {
    if (!effectiveStart || !effectiveEnd) return false
    const start = startOfDay(effectiveStart)
    const end = startOfDay(effectiveEnd)
    const current = startOfDay(day)
    const min = start <= end ? start : end
    const max = start <= end ? end : start
    return current >= min && current <= max
  }

  return (
    <div className="date-range-picker" ref={rootRef}>
      <button
        type="button"
        className="date-range-trigger"
        disabled={disabled}
        aria-expanded={open}
        aria-controls={popoverId}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={onKeyDown}
      >
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden>
          <path d="M19 4h-1V2h-2v2H8V2H6v2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm0 16H5V10h14v10zM5 8V6h14v2H5zm7 4h5v5h-5v-5z" />
        </svg>
        <span className="date-range-trigger-text">
          {formatDisplay(from)} – {formatDisplay(to)}
        </span>
      </button>

      {open ? (
        <div id={popoverId} className="date-range-popover" role="dialog" aria-label="Date range">
          <div className="date-range-popover-header">
            <button type="button" className="date-range-nav" onClick={() => shiftMonth(-1)} aria-label="Previous month">
              ‹
            </button>
            <span className="date-range-month">{monthLabel(viewYear, viewMonth)}</span>
            <button type="button" className="date-range-nav" onClick={() => shiftMonth(1)} aria-label="Next month">
              ›
            </button>
          </div>
          <p className="date-range-hint">
            {phase === 'picking-end' ? 'Select end date' : 'Select start date'}
          </p>
          <div className="date-range-weekdays">
            {weekdayLabels.map((label) => (
              <span key={label}>{label}</span>
            ))}
          </div>
          <div className="date-range-grid">
            {cells.map((day, index) => {
              if (!day) {
                return <span key={`empty-${index}`} className="date-range-day empty" />
              }
              const selectedStart = rangeStart && sameDay(day, rangeStart)
              const selectedFrom = fromDate && phase === 'idle' && sameDay(day, fromDate)
              const selectedTo = toDate && phase === 'idle' && sameDay(day, toDate)
              return (
                <button
                  key={day.toISOString()}
                  type="button"
                  className={[
                    'date-range-day',
                    isInRange(day) ? 'in-range' : '',
                    selectedStart || selectedFrom ? 'range-start' : '',
                    selectedTo ? 'range-end' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  onClick={() => onDayClick(day)}
                >
                  {day.getDate()}
                </button>
              )
            })}
          </div>
        </div>
      ) : null}
    </div>
  )
}
