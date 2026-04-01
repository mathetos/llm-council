import { forwardRef } from 'react'
import { cn } from '../../lib/utils'
import { focusRingClass } from '../../lib/ui'

const stateClass = {
  default: 'border-input',
  focused: 'border-ring ring-2 ring-ring/25',
  error: 'border-destructive',
  disabled: 'border-input bg-muted text-muted-foreground',
}

const sizeClass = {
  sm: 'h-8 text-xs px-3',
  md: 'h-10 text-sm px-3',
  lg: 'h-11 text-sm px-4',
}

export const Input = forwardRef(function Input(
  { state = 'default', inputSize = 'md', className, disabled, ...props },
  ref
) {
  return (
    <input
      ref={ref}
      disabled={disabled}
      className={cn(
        'w-full rounded-md border bg-background text-foreground placeholder:text-muted-foreground transition-colors duration-fast ease-default',
        focusRingClass,
        stateClass[state] || stateClass.default,
        sizeClass[inputSize] || sizeClass.md,
        disabled && stateClass.disabled,
        className
      )}
      {...props}
    />
  )
})
