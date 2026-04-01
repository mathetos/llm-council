import { cn } from '../../lib/utils'

export function DefaultsSummary({ items = [], muted = false, className }) {
  return (
    <div
      className={cn(
        'rounded-md border border-border px-3 py-2 text-xs',
        muted ? 'bg-muted text-muted-foreground' : 'bg-card text-foreground',
        className
      )}
    >
      {items.join(' • ')}
    </div>
  )
}
