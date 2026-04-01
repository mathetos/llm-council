import { cn } from '../../lib/utils'

export function Badge({ className, variant = 'neutral', children }) {
  const variantClass =
    variant === 'accent'
      ? 'border-primary/30 bg-primary/10 text-foreground'
      : 'border-border bg-muted text-muted-foreground'

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium',
        variantClass,
        className
      )}
    >
      {children}
    </span>
  )
}
