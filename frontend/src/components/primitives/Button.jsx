import { Loader2 } from 'lucide-react'
import { cn } from '../../lib/utils'
import { focusRingClass } from '../../lib/ui'

const variantClass = {
  primary: 'bg-primary text-primary-foreground hover:bg-primary/90',
  secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/90',
  accent: 'bg-accent text-accent-foreground hover:bg-accent/90',
  ghost: 'bg-transparent text-foreground hover:bg-muted',
}

const sizeClass = {
  sm: 'h-8 px-3 text-xs',
  md: 'h-10 px-4 text-sm',
  lg: 'h-11 px-5 text-sm',
}

export function Button({
  variant = 'primary',
  size = 'md',
  isLoading = false,
  fullWidth = false,
  className,
  children,
  disabled,
  ...props
}) {
  const isDisabled = disabled || isLoading
  return (
    <button
      type="button"
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors duration-fast ease-default disabled:cursor-not-allowed disabled:opacity-60',
        focusRingClass,
        variantClass[variant] || variantClass.primary,
        sizeClass[size] || sizeClass.md,
        fullWidth && 'w-full',
        className
      )}
      disabled={isDisabled}
      {...props}
    >
      {isLoading ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : null}
      {children}
    </button>
  )
}
