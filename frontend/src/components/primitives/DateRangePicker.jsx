import { useMemo, useState } from 'react'
import { Calendar } from './Calendar'
import { Button } from './Button'
import { Alert } from './Alert'
import { TabBar } from './TabBar'
import { cn } from '../../lib/utils'

function addDays(date, days) {
  const next = new Date(date)
  next.setDate(next.getDate() + days)
  return next
}

function startOfDay(date) {
  if (!date) return null
  return new Date(date.getFullYear(), date.getMonth(), date.getDate())
}

function daysBetween(a, b) {
  return Math.floor((startOfDay(b) - startOfDay(a)) / (1000 * 60 * 60 * 24))
}

function formatRange(value) {
  if (!value?.start || !value?.end) return 'No range selected'
  return `${value.start.toLocaleDateString()} - ${value.end.toLocaleDateString()}`
}

const presetOptions = [
  { value: '7', label: '7 days' },
  { value: '14', label: '14 days' },
  { value: '30', label: '30 days' },
  { value: 'custom', label: 'Custom' },
]

export function DateRangePicker({
  label,
  value = { start: null, end: null },
  onChange,
  variant = 'compact',
  earliestStart = null,
  maxRange = 30,
  maxHorizon = 90,
}) {
  const [activePreset, setActivePreset] = useState('custom')
  const [anchor, setAnchor] = useState(null)
  const [error, setError] = useState('')
  const min = startOfDay(earliestStart || new Date())
  const max = addDays(min, maxHorizon)

  const summary = useMemo(() => formatRange(value), [value])

  const setPreset = (next) => {
    setActivePreset(next)
    if (next === 'custom') return
    const days = Number.parseInt(next, 10)
    if (!Number.isFinite(days)) return
    const start = startOfDay(min)
    const end = addDays(start, Math.max(days - 1, 0))
    onChange?.({ start, end })
    setError('')
  }

  const handleDateSelect = (selected) => {
    if (!selected) return
    if (!anchor || (value?.start && value?.end)) {
      setAnchor(selected)
      onChange?.({ start: selected, end: null })
      return
    }
    const start = selected < anchor ? selected : anchor
    const end = selected < anchor ? anchor : selected
    if (daysBetween(start, end) + 1 > maxRange) {
      setError(`Range cannot exceed ${maxRange} days.`)
      return
    }
    onChange?.({ start, end })
    setAnchor(null)
    setError('')
  }

  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4">
      <div className="text-sm font-medium text-foreground">{label}</div>
      <TabBar value={activePreset} onChange={setPreset} options={presetOptions} size="sm" />
      <div className="text-xs text-muted-foreground">{summary}</div>
      {error ? (
        <Alert variant="error" title="Invalid range">
          {error}
        </Alert>
      ) : null}
      <div className={cn('grid gap-3', variant === 'expanded' ? 'grid-cols-1 lg:grid-cols-2' : 'grid-cols-1')}>
        <Calendar
          selectedDate={value?.start}
          onDateSelect={handleDateSelect}
          minDate={min}
          maxDate={max}
          disablePast
          highlightRange={value}
        />
        {variant === 'expanded' ? (
          <div className="space-y-2 rounded-md border border-border bg-muted/30 p-3 text-sm text-muted-foreground">
            <p>Earliest start: {min.toLocaleDateString()}</p>
            <p>Max range: {maxRange} days</p>
            <p>Max horizon: {maxHorizon} days</p>
            <Button variant="ghost" size="sm" onClick={() => onChange?.({ start: null, end: null })}>
              Clear range
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  )
}
