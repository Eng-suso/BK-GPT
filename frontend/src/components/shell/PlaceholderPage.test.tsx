import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { PlaceholderPage } from '../shell/PlaceholderPage';

describe('PlaceholderPage', () => {
  it('renders title and description', () => {
    render(
      <PlaceholderPage title="Test Title" description="Test description text" />
    );

    expect(screen.getByRole('heading', { name: /test title/i })).toBeInTheDocument();
    expect(screen.getByText('Test description text')).toBeInTheDocument();
  });

  it('renders items list when items are provided', () => {
    const items = ['Item A', 'Item B', 'Item C'];
    render(
      <PlaceholderPage title="Title" description="Desc" items={items} />
    );

    items.forEach((item) => {
      expect(screen.getByText(item)).toBeInTheDocument();
    });
  });

  it('does not render list when items array is empty', () => {
    render(<PlaceholderPage title="Title" description="Desc" items={[]} />);
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
  });

  it('renders the "UI draft" eyebrow label', () => {
    render(<PlaceholderPage title="Title" description="Desc" />);
    expect(screen.getByText('UI draft')).toBeInTheDocument();
  });
});
