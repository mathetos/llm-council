import { cn } from '../../lib/utils'

export function Tooltip({ text, show, position = 'top', className }) {
  if (!show) return null
  const positionClass =
    position === 'right'
      ? 'left-full ml-2 top-1/2 -translate-y-1/2'
      : position === 'bottom'
      ? 'top-full mt-2 left-1/2 -translate-x-1/2'
      : 'bottom-full mb-2 left-1/2 -translate-x-1/2'

  return (
    <span
      role="tooltip"
      className={cn(
        'pointer-events-none absolute z-50 block rounded px-2 py-1 text-xs',
        'bg-[hsl(var(--ring))] text-white shadow-md',
        'transition-opacity duration-fast ease-default break-words',
        positionClass,
        className
      )}
    >
      {text}
    </span>
  )
}
