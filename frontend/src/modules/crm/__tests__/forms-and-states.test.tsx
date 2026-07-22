import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LeadForm } from '../forms';
import { AIInsights } from '../components/AIInsights';
import { GovernedError } from '../components/CrmPage';
import { CrmApiError } from '../services/crm-service';

describe('CRM forms and governed states', () => {
  it('retains lead form data and reports inline validation', () => {
    const submit = vi.fn(); render(<LeadForm pending={false} onSubmit={submit}/>,{wrapper:MemoryRouter});
    fireEvent.change(screen.getByLabelText('Email'),{target:{value:'not-an-email'}});
    fireEvent.click(screen.getByRole('button',{name:'Save lead'}));
    expect(screen.getByText('Last name is required.')).toBeInTheDocument();
    expect(screen.getByText('Enter a valid email address.')).toBeInTheDocument();
    expect(screen.getByLabelText('Email')).toHaveValue('not-an-email');
    expect(submit).not.toHaveBeenCalled();
  });

  it('renders permission and correlation details without leaking a generic zero state', () => {
    render(<GovernedError subject="Lead" error={new CrmApiError('Denied','permission',403,'permission_denied','req-denied')}/>);
    expect(screen.getByText('Access denied')).toBeInTheDocument();
    expect(screen.getByText(/req-denied/u)).toBeInTheDocument();
  });

  it('shows prediction unavailable instead of fabricated insights', () => {
    render(<AIInsights prediction={null}/>);
    expect(screen.getByText('Provider prediction unavailable')).toBeInTheDocument();
    expect(screen.getByText(/never presented as AI output/u)).toBeInTheDocument();
  });
});
