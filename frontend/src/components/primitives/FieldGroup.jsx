import { Input } from './Input'
import { cn } from '../../lib/utils'
import { focusRingClass } from '../../lib/ui'

export function FieldGroup({
  label,
  helperText,
  errorMessage,
  required = false,
  inputProps = {},
  className,
}) {
  const hasError = Boolean(errorMessage)
  const inputId = inputProps.id
  return (
    <div className={cn('space-y-1.5', className)}>
      <label htmlFor={inputId} className="text-sm font-medium text-foreground">
        {label}
        {required ? <span className="ml-1 text-destructive">*</span> : null}
      </label>
      <div className={cn('rounded-md', focusRingClass)}>
        <Input
          {...inputProps}
          state={hasError ? 'error' : inputProps.state}
          className={cn('focus-visible:ring-0', inputProps.className)}
        />
      </div>
      {hasError ? (
        <p className="text-xs text-destructive" role="alert">
          {errorMessage}
        </p>
      ) : helperText ? (
        <p className="text-xs text-muted-foreground">{helperText}</p>
      ) : null}
    </div>
  )
}
