import { useState } from 'react'
import { Tooltip } from './Tooltip'
import { cn } from '../../lib/utils'
import { focusRingClass } from '../../lib/ui'

const variantClass = {
  default: 'text-muted-foreground hover:bg-primary/10 hover:text-primary',
  destructive: 'text-muted-foreground hover:bg-destructive/10 hover:text-destructive',
}

export function IconAction({ icon, tooltip, onClick, href, variant = 'default', className }) {
  const [showTooltip, setShowTooltip] = useState(false)
  const classes = cn(
    'relative inline-flex size-8 items-center justify-center rounded-md transition-colors duration-fast ease-default',
    focusRingClass,
    variantClass[variant] || variantClass.default,
    className
  )

  if (href) {
    return (
      <a
        href={href}
        className={classes}
        aria-label={tooltip}
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        onFocus={() => setShowTooltip(true)}
        onBlur={() => setShowTooltip(false)}
      >
        {icon}
        <Tooltip text={tooltip} show={showTooltip} />
      </a>
    )
  }

  return (
    <button
      type="button"
      className={classes}
      aria-label={tooltip}
      onClick={onClick}
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
      onFocus={() => setShowTooltip(true)}
      onBlur={() => setShowTooltip(false)}
    >
      {icon}
      <Tooltip text={tooltip} show={showTooltip} />
    </button>
  )
}
