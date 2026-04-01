import { cn } from '../../lib/utils'
import { focusRingClass } from '../../lib/ui'

const sizeClass = {
  sm: 'h-8 text-xs px-3',
  md: 'h-9 text-sm px-3.5',
}

export function TabBar({ value, onChange, options = [], size = 'md', className }) {
  return (
    <div className={cn('inline-flex rounded-md border border-border bg-muted p-1', className)} role="tablist">
      {options.map((option) => {
        const active = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange?.(option.value)}
            className={cn(
              'rounded-md font-medium transition-colors duration-fast ease-default',
              focusRingClass,
              sizeClass[size] || sizeClass.md,
              active
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}
