/**
 * SPDX-License-Identifier: Apache-2.0
 *
 * ErrorBoundary Component
 *
 * Catches React component errors and displays a fallback UI.
 */
import type { ReactNode } from 'react';
import { Component } from 'react';
import { ErrorState } from './ui/ErrorState';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // Only log in development to reduce console noise in production
    if (import.meta.env.DEV) {
      console.error('ErrorBoundary caught an error:', error, errorInfo);
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-background">
          <ErrorState
            title="Application Error"
            message="An unexpected error occurred. Please refresh the page or contact support if the problem persists."
          />
        </div>
      );
    }

    return this.props.children;
  }
}
