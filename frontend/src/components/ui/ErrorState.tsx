/**
 * SPDX-License-Identifier: Apache-2.0
 *
 * ErrorState Component
 *
 * Displays an error state with icon, title, message, and optional retry action.
 */
import { AlertCircle, RefreshCw } from 'lucide-react';
import { Button } from './Button';

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  className?: string;
}

export const ErrorState = ({ 
  title = "Something went wrong", 
  message, 
  onRetry,
  className 
}: ErrorStateProps) => {
  return (
    <div className={`flex flex-col items-center justify-center min-h-[400px] text-center p-8 ${className ?? ''}`}>
      <div className="bg-destructive/10 rounded-full p-4 mb-4">
        <AlertCircle className="w-12 h-12 text-destructive" />
      </div>
      <h3 className="text-lg font-semibold text-foreground mb-2">{title}</h3>
      <p className="text-muted-foreground max-w-md mb-6">{message}</p>
      {onRetry && (
        <Button onClick={onRetry} variant="secondary">
          <RefreshCw className="w-4 h-4 mr-2" />
          Try Again
        </Button>
      )}
    </div>
  );
};
