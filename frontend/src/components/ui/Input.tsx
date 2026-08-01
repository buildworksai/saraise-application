/**
 * Input Component
 *
 * Reusable input component with error handling.
 */
import type { InputHTMLAttributes } from "react";
import { forwardRef, useId } from "react";
import { clsx } from "clsx";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  error?: string;
  label?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, error, id, label, ...props }, ref) => {
    const generatedId = useId();
    const inputId = id ?? (label ? generatedId : undefined);
    const errorId = inputId ? `${inputId}-error` : undefined;
    return (
      <div className="w-full">
        {label && (
          <label htmlFor={inputId} className="block text-sm font-medium text-foreground mb-1">
            {label}
          </label>
        )}
        <input
          id={inputId}
          ref={ref}
          className={clsx(
            // Root-cause fix: semantic tokens (no hardcoded grays/blues).
            "block w-full px-3 py-2 rounded-md border bg-background text-foreground shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ring-offset-background",
            error ? "border-destructive" : "border-input",
            className
          )}
          {...props}
        />
        {error && (
          <p id={errorId} className="mt-1 text-sm text-destructive">
            {error}
          </p>
        )}
      </div>
    );
  }
);

Input.displayName = "Input";
