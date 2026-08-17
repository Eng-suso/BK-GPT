import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { TopBar } from '../shell/TopBar';

describe('TopBar', () => {
  it('renders the section title for "home"', () => {
    render(<TopBar activeSection="home" />);
    expect(screen.getByRole('heading', { level: 1, name: /home/i })).toBeInTheDocument();
  });

  it('renders "Area lavoro" eyebrow label', () => {
    render(<TopBar activeSection="home" />);
    expect(screen.getByText('Area lavoro')).toBeInTheDocument();
  });

  it('renders "Clienti" heading when activeSection is "clients"', () => {
    render(<TopBar activeSection="clients" />);
    expect(screen.getByRole('heading', { level: 1, name: /clienti/i })).toBeInTheDocument();
  });

  it('renders action buttons (Cerca and avatar)', () => {
    render(<TopBar activeSection="home" />);
    expect(screen.getByRole('button', { name: /cerca/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /profilo utente/i })).toBeInTheDocument();
  });
});
