import { cn } from '../../lib/utils'

export function PresetOrCustomPicker({
  label,
  presets = [],
  value,
  onChange,
  customInput = null,
  disabled = false,
  className,
}) {
  const isCustom = value === 'custom'

  return (
    <div className={cn('space-y-2', className)}>
      <p className="text-sm font-medium text-foreground">{label}</p>
      <div className="flex flex-wrap gap-2">
        {presets.map((preset) => (
          <button
            key={preset.value}
            type="button"
            disabled={disabled}
            onClick={() => onChange?.(preset.value)}
            className={cn(
              'rounded-md border px-3 py-1.5 text-xs font-medium transition-colors duration-fast ease-default',
              value === preset.value
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border bg-card text-foreground hover:bg-muted',
              disabled && 'cursor-not-allowed opacity-60'
            )}
          >
            {preset.label}
          </button>
        ))}
        <button
          type="button"
          disabled={disabled}
          onClick={() => onChange?.('custom')}
          className={cn(
            'rounded-md border px-3 py-1.5 text-xs font-medium transition-colors duration-fast ease-default',
            isCustom
              ? 'border-primary bg-primary/10 text-primary'
              : 'border-border bg-card text-foreground hover:bg-muted',
            disabled && 'cursor-not-allowed opacity-60'
          )}
        >
          Custom
        </button>
      </div>
      {isCustom ? customInput : null}
    </div>
  )
}
