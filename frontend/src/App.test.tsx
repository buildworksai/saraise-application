import { render, screen } from '@testing-library/react';
import App from './App';

describe('App', () => {
  it('renders the app with router', () => {
    render(<App />);
    // App renders BrowserRouter, so check for a link or route element
    // The login page should be accessible
    expect(screen.getByRole('link', { name: /forgot password/i })).toBeInTheDocument();
  });
});
