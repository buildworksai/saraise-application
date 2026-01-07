/**
 * PasswordField Component Tests
 */

import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PasswordField } from './PasswordField';

describe('PasswordField', () => {
  it('should render password input', () => {
    render(<PasswordField id="password" label="Password" />);
    const input = screen.getByLabelText(/^password$/i) as HTMLInputElement;
    expect(input.type).toBe('password');
  });

  it('should toggle password visibility', async () => {
    const user = userEvent.setup();
    render(<PasswordField id="password" label="Password" />);
    
    const input = screen.getByLabelText(/^password$/i) as HTMLInputElement;
    const toggleButton = screen.getByRole('button');
    
    expect(input.type).toBe('password');
    
    await user.click(toggleButton);
    expect(input.type).toBe('text');
    
    await user.click(toggleButton);
    expect(input.type).toBe('password');
  });

  it('should display error message', () => {
    render(<PasswordField id="password" label="Password" error="Password is required" />);
    expect(screen.getByText('Password is required')).toBeInTheDocument();
  });

  it('should display helper text', () => {
    render(<PasswordField id="password" label="Password" helperText="Must be 8+ characters" />);
    expect(screen.getByText('Must be 8+ characters')).toBeInTheDocument();
  });

  it('should call onChange when value changes', async () => {
    const user = userEvent.setup();
    const handleChange = vi.fn();
    render(<PasswordField id="password" label="Password" onChange={handleChange} />);
    
    const input = screen.getByLabelText(/^password$/i);
    await user.type(input, 'test123');
    
    expect(handleChange).toHaveBeenCalled();
  });
});

