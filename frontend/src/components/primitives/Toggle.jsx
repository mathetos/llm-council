import * as Switch from '@radix-ui/react-switch'
import { cn } from '../../lib/utils'
import { focusRingClass } from '../../lib/ui'

export function Toggle({ id, label, className, checked, onCheckedChange, disabled = false }) {
  return (
    <label
      htmlFor={id}
      className={cn(
        'inline-flex w-full items-center justify-between gap-3 rounded-md border border-border bg-card px-3 py-2 text-sm',
        disabled && 'cursor-not-allowed opacity-60',
        className
      )}
    >
      <span className="text-foreground">{label}</span>
      <Switch.Root
        id={id}
        checked={checked}
        disabled={disabled}
        onCheckedChange={onCheckedChange}
        className={cn(
          'relative h-5 w-9 rounded-full border border-border bg-secondary transition-colors duration-fast ease-default',
          'data-[state=checked]:border-primary data-[state=checked]:bg-primary',
          focusRingClass
        )}
        aria-label={label}
      >
        <Switch.Thumb
          className={cn(
            'block size-4 translate-x-0.5 rounded-full bg-background shadow-sm transition-transform duration-fast ease-default',
            'data-[state=checked]:translate-x-4 data-[state=checked]:bg-primary-foreground'
          )}
        />
      </Switch.Root>
    </label>
  )
}
