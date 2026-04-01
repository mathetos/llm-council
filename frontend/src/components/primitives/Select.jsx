import { ChevronDown } from 'lucide-react'
import { cn } from '../../lib/utils'
import { focusRingClass } from '../../lib/ui'

export function Select({
  id,
  options = [],
  placeholder = 'Select an option',
  value,
  onChange,
  state = 'default',
  disabled = false,
  className,
  ...props
}) {
  return (
    <div className={cn('relative', className)}>
      <select
        id={id}
        value={value}
        onChange={onChange}
        disabled={disabled}
        className={cn(
          'h-10 w-full appearance-none rounded-md border bg-background px-3 pr-9 text-sm text-foreground transition-colors duration-fast ease-default',
          'disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground',
          state === 'error' ? 'border-destructive' : 'border-input',
          focusRingClass
        )}
        {...props}
      >
        <option value="" disabled hidden>
          {placeholder}
        </option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <ChevronDown
        className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
        aria-hidden="true"
      />
    </div>
  )
}
