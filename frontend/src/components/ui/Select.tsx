/**
 * Select Component
 * 
 * Reusable select component with error handling.
 */
import type { SelectHTMLAttributes} from 'react';
import { forwardRef } from 'react';
import { clsx } from 'clsx';

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  error?: string;
  label?: string;
  options: { value: string; label: string }[];
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, error, label, options, ...props }, ref) => {
    return (
      <div className="w-full">
        {label && (
          <label htmlFor={props.id} className="block text-sm font-medium text-foreground mb-1">
            {label}
          </label>
        )}
        <select
          ref={ref}
          className={clsx(
            // Root-cause fix: semantic tokens (no hardcoded grays/blues).
            'block w-full px-3 py-2 rounded-md border bg-background text-foreground shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ring-offset-background',
            error
              ? 'border-destructive'
              : 'border-input',
            className
          )}
          {...props}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        {error && (
          <p className="mt-1 text-sm text-destructive">{error}</p>
        )}
      </div>
    );
  }
);

Select.displayName = 'Select';

