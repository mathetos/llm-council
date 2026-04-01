import * as Collapsible from '@radix-ui/react-collapsible'
import { ChevronDown } from 'lucide-react'
import { cn } from '../../lib/utils'
import { focusRingClass } from '../../lib/ui'

export function Accordion({ title, description, trailing, children, defaultOpen = false, className }) {
  return (
    <Collapsible.Root defaultOpen={defaultOpen} className={cn('rounded-lg border border-border bg-card', className)}>
      <Collapsible.Trigger
        className={cn(
          'group flex w-full items-center justify-between gap-2 rounded-lg px-4 py-3 text-left',
          'text-foreground hover:bg-muted/50',
          focusRingClass
        )}
      >
        <div className="min-w-0">
          <div className="text-sm font-semibold">{title}</div>
          {description ? <div className="text-xs text-muted-foreground">{description}</div> : null}
        </div>
        <div className="flex items-center gap-2">
          {trailing ? <span className="text-xs text-muted-foreground">{trailing}</span> : null}
          <ChevronDown className="size-4 text-muted-foreground transition-transform duration-fast ease-default group-data-[state=open]:rotate-180" />
        </div>
      </Collapsible.Trigger>
      <Collapsible.Content className="border-t border-border px-4 py-3">
        {children}
      </Collapsible.Content>
    </Collapsible.Root>
  )
}
