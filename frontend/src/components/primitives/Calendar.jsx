import { useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { cn } from '../../lib/utils'
import { focusRingClass } from '../../lib/ui'

function startOfDay(date) {
  if (!date) return null
  return new Date(date.getFullYear(), date.getMonth(), date.getDate())
}

function isSameDay(a, b) {
  if (!a || !b) return false
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  )
}

function buildMonthGrid(baseDate) {
  const year = baseDate.getFullYear()
  const month = baseDate.getMonth()
  const first = new Date(year, month, 1)
  const firstWeekday = first.getDay()
  const start = new Date(year, month, 1 - firstWeekday)

  const days = []
  for (let i = 0; i < 42; i += 1) {
    days.push(new Date(start.getFullYear(), start.getMonth(), start.getDate() + i))
  }
  return days
}

const weekdayLabels = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']

export function Calendar({
  selectedDate = null,
  onDateSelect,
  minDate = null,
  maxDate = null,
  disablePast = false,
  highlightRange = null,
}) {
  const [currentMonth, setCurrentMonth] = useState(() => startOfDay(selectedDate) || new Date())
  const days = useMemo(() => buildMonthGrid(currentMonth), [currentMonth])
  const today = startOfDay(new Date())
  const min = startOfDay(minDate)
  const max = startOfDay(maxDate)
  const rangeStart = startOfDay(highlightRange?.start)
  const rangeEnd = startOfDay(highlightRange?.end)

  const monthLabel = currentMonth.toLocaleDateString(undefined, {
    month: 'long',
    year: 'numeric',
  })

  const canSelect = (date) => {
    const day = startOfDay(date)
    if (disablePast && day < today) return false
    if (min && day < min) return false
    if (max && day > max) return false
    return true
  }

  return (
    <div className="w-[320px] rounded-lg border border-border bg-card p-3">
      <div className="mb-2 flex items-center justify-between">
        <button
          type="button"
          className={cn('rounded-md p-1 hover:bg-muted', focusRingClass)}
          onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1, 1))}
          aria-label="Previous month"
        >
          <ChevronLeft className="size-4" />
        </button>
        <div className="text-sm font-semibold text-foreground">{monthLabel}</div>
        <button
          type="button"
          className={cn('rounded-md p-1 hover:bg-muted', focusRingClass)}
          onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 1))}
          aria-label="Next month"
        >
          <ChevronRight className="size-4" />
        </button>
      </div>

      <div className="mb-1 grid grid-cols-7 text-center text-xs text-muted-foreground">
        {weekdayLabels.map((label) => (
          <div key={label} className="py-1">
            {label}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-1">
        {days.map((date) => {
          const inMonth = date.getMonth() === currentMonth.getMonth()
          const disabled = !canSelect(date)
          const selected = isSameDay(selectedDate, date)
          const inRange =
            rangeStart && rangeEnd && startOfDay(date) >= rangeStart && startOfDay(date) <= rangeEnd

          return (
            <button
              key={date.toISOString()}
              type="button"
              disabled={disabled}
              onClick={() => onDateSelect?.(startOfDay(date))}
              className={cn(
                'h-9 rounded-md text-xs transition-colors duration-fast ease-default',
                focusRingClass,
                !inMonth && 'text-muted-foreground/60',
                disabled && 'cursor-not-allowed opacity-40',
                inRange && 'bg-accent/30',
                selected
                  ? 'bg-primary text-primary-foreground hover:bg-primary'
                  : 'text-foreground hover:bg-muted'
              )}
              aria-pressed={selected}
            >
              {date.getDate()}
            </button>
          )
        })}
      </div>
    </div>
  )
}
