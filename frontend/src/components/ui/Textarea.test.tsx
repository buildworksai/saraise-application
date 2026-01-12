/**
 * Textarea Component Tests
 */

import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Textarea } from './Textarea';

describe('Textarea', () => {
  it('should render textarea element', () => {
    render(<Textarea />);
    const textarea = screen.getByRole('textbox');
    expect(textarea).toBeInTheDocument();
    expect(textarea.tagName).toBe('TEXTAREA');
  });

  it('should render with label', () => {
    render(<Textarea label="Description" id="description" />);
    expect(screen.getByLabelText('Description')).toBeInTheDocument();
  });

  it('should display error message', () => {
    render(<Textarea error="This field is required" />);
    expect(screen.getByText('This field is required')).toBeInTheDocument();
  });

  it('should apply error styling when error is present', () => {
    const { container } = render(<Textarea error="Error" />);
    const textarea = container.querySelector('textarea');
    expect(textarea?.className).toContain('border-destructive');
  });

  it('should forward ref', () => {
    const ref = { current: null };
    render(<Textarea ref={ref} />);
    expect(ref.current).toBeInstanceOf(HTMLTextAreaElement);
  });

  it('should accept all standard textarea props', () => {
    render(<Textarea placeholder="Enter text" rows={5} readOnly />);
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    expect(textarea.placeholder).toBe('Enter text');
    expect(textarea.rows).toBe(5);
    expect(textarea.readOnly).toBe(true);
  });
});
