import { AlertCircle, AlertTriangle, CheckCircle2, Info } from 'lucide-react'
import { cn } from '../../lib/utils'

const variantMap = {
  info: {
    box: 'border-primary/30 bg-primary/10 text-foreground',
    icon: Info,
  },
  warning: {
    box: 'border-primary/25 bg-secondary text-foreground',
    icon: AlertTriangle,
  },
  error: {
    box: 'border-destructive/40 bg-destructive/10 text-foreground',
    icon: AlertCircle,
  },
  success: {
    box: 'border-accent/40 bg-accent/20 text-foreground',
    icon: CheckCircle2,
  },
}

export function Alert({ variant = 'info', title, children, className }) {
  const config = variantMap[variant] || variantMap.info
  const Icon = config.icon

  return (
    <div className={cn('rounded-md border p-3', config.box, className)} role="status">
      <div className="flex items-start gap-2">
        <Icon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <div className="space-y-1">
          {title ? <div className="text-sm font-semibold">{title}</div> : null}
          <div className="text-sm text-muted-foreground">{children}</div>
        </div>
      </div>
    </div>
  )
}
