import { ArrowLeft } from 'lucide-react'
import { cn } from '../../lib/utils'
import { focusRingClass } from '../../lib/ui'

const variantClass = {
  primary: 'text-primary hover:text-primary/90',
  destructive: 'text-destructive hover:text-destructive/90',
  muted: 'text-muted-foreground hover:text-foreground',
}

export function TextLink({
  as = 'a',
  href,
  variant = 'primary',
  backArrow = false,
  className,
  children,
  ...props
}) {
  const classes = cn(
    'inline-flex items-center gap-1 text-sm underline-offset-2 hover:underline',
    focusRingClass,
    variantClass[variant] || variantClass.primary,
    className
  )

  if (as === 'button') {
    return (
      <button type="button" className={classes} {...props}>
        {backArrow ? <ArrowLeft className="size-3.5" aria-hidden="true" /> : null}
        {children}
      </button>
    )
  }

  return (
    <a href={href} className={classes} {...props}>
      {backArrow ? <ArrowLeft className="size-3.5" aria-hidden="true" /> : null}
      {children}
    </a>
  )
}
