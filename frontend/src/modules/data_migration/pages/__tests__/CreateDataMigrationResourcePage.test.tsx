import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { CreateDataMigrationJobPage } from '../CreateDataMigrationJobPage';

describe('CreateDataMigrationJobPage', () => {
  it('reveals only source-specific fields and prevents invalid combinations', async () => {
    const user = userEvent.setup();
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><CreateDataMigrationJobPage /></MemoryRouter></QueryClientProvider>);
    expect(screen.getByLabelText('DMS artifact version ID')).toBeInTheDocument();
    expect(screen.queryByLabelText('Named connection')).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Source type'), 'api');
    expect(screen.getByLabelText('Named connection')).toBeInTheDocument();
    expect(screen.getByLabelText('Relative path')).toBeInTheDocument();
    expect(screen.queryByLabelText('DMS artifact version ID')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /target/i })).toBeDisabled();
  });
});
