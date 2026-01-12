/**
 * SPDX-License-Identifier: Apache-2.0
 */

import { useMemo, useState } from 'react'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Eye, EyeOff, AlertTriangle } from 'lucide-react'
import { cn } from '@/lib/utils'

interface PasswordFieldProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'> {
  id: string
  label: string
  error?: string | null
  helperText?: string
}

export function PasswordField({
  id,
  label,
  error,
  helperText,
  className,
  onKeyUp,
  ...props
}: PasswordFieldProps) {
  const [isVisible, setIsVisible] = useState(false)
  const [isCapsLockOn, setIsCapsLockOn] = useState(false)

  const describedBy = useMemo(() => {
    const ids: string[] = []
    if (helperText) ids.push(`${id}-helper`)
    if (error) ids.push(`${id}-error`)
    if (isCapsLockOn) ids.push(`${id}-caps`)
    return ids.join(' ') || undefined
  }, [error, helperText, id, isCapsLockOn])

  return (
    <div className="space-y-2">
      <Label htmlFor={id} className="text-sm font-semibold">
        {label}
      </Label>
      <div className="relative">
        <Input
          id={id}
          type={isVisible ? 'text' : 'password'}
          aria-invalid={error ? 'true' : 'false'}
          aria-describedby={describedBy}
          className={cn('pr-12 h-11', className)}
          onKeyUp={(event) => {
            setIsCapsLockOn(event.getModifierState('CapsLock'))
            onKeyUp?.(event)
          }}
          {...props}
        />
        <button
          type="button"
          onClick={() => setIsVisible((prev) => !prev)}
          className="absolute inset-y-0 right-3 flex items-center text-gray-500 hover:text-gray-800 dark:hover:text-gray-200"
          aria-label={isVisible ? 'Hide password' : 'Show password'}
        >
          {isVisible ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
        </button>
      </div>
      {helperText && !error && (
        <p id={`${id}-helper`} className="text-xs text-muted-foreground">
          {helperText}
        </p>
      )}
      {isCapsLockOn && (
        <p id={`${id}-caps`} className="text-xs text-amber-600 dark:text-amber-400 flex items-center gap-1" role="status">
          <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
          Caps Lock is on
        </p>
      )}
      {error && (
        <p
          id={`${id}-error`}
          className="text-xs text-red-600 dark:text-red-400 font-medium"
          role="alert"
          aria-live="polite"
        >
          {error}
        </p>
      )}
    </div>
  )
}
