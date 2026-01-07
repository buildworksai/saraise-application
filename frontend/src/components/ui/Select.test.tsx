/**
 * Select Component Tests
 */

import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Select } from './Select';

describe('Select', () => {
  const options = [
    { value: 'option1', label: 'Option 1' },
    { value: 'option2', label: 'Option 2' },
    { value: 'option3', label: 'Option 3' },
  ];

  it('should render select element', () => {
    render(<Select options={options} />);
    const select = screen.getByRole('combobox');
    expect(select).toBeInTheDocument();
  });

  it('should render with label', () => {
    render(<Select label="Choose option" options={options} id="select" />);
    expect(screen.getByLabelText('Choose option')).toBeInTheDocument();
  });

  it('should render all options', () => {
    render(<Select options={options} />);
    expect(screen.getByText('Option 1')).toBeInTheDocument();
    expect(screen.getByText('Option 2')).toBeInTheDocument();
    expect(screen.getByText('Option 3')).toBeInTheDocument();
  });

  it('should display error message', () => {
    render(<Select options={options} error="Please select an option" />);
    expect(screen.getByText('Please select an option')).toBeInTheDocument();
  });

  it('should apply error styling when error is present', () => {
    const { container } = render(<Select options={options} error="Error" />);
    const select = container.querySelector('select');
    expect(select?.className).toContain('border-destructive');
  });

  it('should forward ref', () => {
    const ref = { current: null };
    render(<Select options={options} ref={ref} />);
    expect(ref.current).toBeInstanceOf(HTMLSelectElement);
  });

  it('should accept value prop', () => {
    render(<Select options={options} value="option2" />);
    const select = screen.getByRole('combobox') as HTMLSelectElement;
    expect(select.value).toBe('option2');
  });

  it('should be disabled when disabled prop is set', () => {
    render(<Select options={options} disabled />);
    const select = screen.getByRole('combobox') as HTMLSelectElement;
    expect(select.disabled).toBe(true);
  });
});

