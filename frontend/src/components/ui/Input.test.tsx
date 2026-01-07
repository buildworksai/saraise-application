/**
 * Input Component Tests
 */

import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Input } from './Input';

describe('Input', () => {
  it('should render input element', () => {
    render(<Input />);
    const input = screen.getByRole('textbox');
    expect(input).toBeInTheDocument();
  });

  it('should render with label', () => {
    render(<Input label="Email" id="email" />);
    expect(screen.getByLabelText('Email')).toBeInTheDocument();
  });

  it('should display error message', () => {
    render(<Input error="This field is required" />);
    expect(screen.getByText('This field is required')).toBeInTheDocument();
  });

  it('should apply error styling when error is present', () => {
    const { container } = render(<Input error="Error" />);
    const input = container.querySelector('input');
    expect(input?.className).toContain('border-destructive');
  });

  it('should forward ref', () => {
    const ref = { current: null };
    render(<Input ref={ref} />);
    expect(ref.current).toBeInstanceOf(HTMLInputElement);
  });

  it('should accept all standard input props', () => {
    render(<Input type="email" placeholder="Enter email" value="test@example.com" readOnly />);
    const input = screen.getByRole('textbox') as HTMLInputElement;
    expect(input.type).toBe('email');
    expect(input.placeholder).toBe('Enter email');
    expect(input.value).toBe('test@example.com');
    expect(input.readOnly).toBe(true);
  });

  it('should not show error when error is not provided', () => {
    render(<Input />);
    expect(screen.queryByText(/error/i)).not.toBeInTheDocument();
  });
});

