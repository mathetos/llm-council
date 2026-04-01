import { Toggle } from './Toggle'
import { cn } from '../../lib/utils'

export function ToggleRevealRow({
  label,
  summary,
  checked,
  onCheckedChange,
  disabled = false,
  children,
  className,
}) {
  return (
    <div className={cn('space-y-2', className)}>
      <Toggle
        id={`toggle-row-${label?.toLowerCase().replace(/\s+/g, '-') || 'item'}`}
        label={label}
        checked={checked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
      />
      {checked ? (
        <div className="rounded-md border border-border bg-card p-3">{children}</div>
      ) : (
        <p className="text-xs text-muted-foreground">{summary}</p>
      )}
    </div>
  )
}
