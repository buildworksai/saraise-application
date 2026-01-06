/**
 * Textarea Component
 *
 * Root-cause fix: semantic tokens for dark/light/system theme consistency.
 */
import type { TextareaHTMLAttributes} from 'react';
import { forwardRef } from 'react';
import { clsx } from 'clsx';

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  error?: string;
  label?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, error, label, ...props }, ref) => {
    return (
      <div className="w-full">
        {label && (
          <label htmlFor={props.id} className="block text-sm font-medium text-foreground mb-1">
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          className={clsx(
            'block w-full px-3 py-2 rounded-md border bg-background text-foreground shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ring-offset-background',
            error ? 'border-destructive' : 'border-input',
            className
          )}
          {...props}
        />
        {error && <p className="mt-1 text-sm text-destructive">{error}</p>}
      </div>
    );
  }
);

Textarea.displayName = 'Textarea';


