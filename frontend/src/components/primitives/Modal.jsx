import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { Button } from './Button'
import { Alert } from './Alert'
import { cn } from '../../lib/utils'
import { focusRingClass } from '../../lib/ui'

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  contentClassName = '',
  primaryAction = 'Save',
  secondaryAction = 'Cancel',
  onPrimaryAction,
  onSecondaryAction,
  isLoading = false,
  errorMessage = '',
}) {
  return (
    <Dialog.Root open={open} onOpenChange={(next) => (!next ? onClose?.() : null)}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[1200] bg-black/45" />
        <Dialog.Content
          className={cn(
            'fixed left-1/2 top-1/2 z-[1201] w-[min(640px,calc(100%-40px))] -translate-x-1/2 -translate-y-1/2',
            'rounded-xl border border-border bg-card p-5 shadow-xl'
            ,
            contentClassName
          )}
        >
          <div className="mb-3 flex items-start justify-between gap-3">
            <div>
              <Dialog.Title className="font-semibold text-foreground">{title}</Dialog.Title>
              {description ? (
                <Dialog.Description className="mt-1 text-[length:var(--font-size-1b)] text-muted-foreground">
                  {description}
                </Dialog.Description>
              ) : null}
            </div>
            <Dialog.Close asChild>
              <button
                type="button"
                className={cn(
                  'rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground',
                  focusRingClass
                )}
                aria-label="Close dialog"
                onClick={() => onClose?.()}
              >
                <X className="size-4" />
              </button>
            </Dialog.Close>
          </div>

          <div className="space-y-4">
            {children}
            {errorMessage ? (
              <Alert variant="error" title="Unable to continue">
                {errorMessage}
              </Alert>
            ) : null}
          </div>

          {(primaryAction || secondaryAction) ? (
            <div className="mt-5 flex items-center justify-end gap-2">
              {secondaryAction ? (
                <Button variant="ghost" onClick={onSecondaryAction}>
                  {secondaryAction}
                </Button>
              ) : null}
              {primaryAction ? (
                <Button variant="primary" isLoading={isLoading} onClick={onPrimaryAction}>
                  {primaryAction}
                </Button>
              ) : null}
            </div>
          ) : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
