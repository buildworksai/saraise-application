/**
 * Skeleton Component Tests
 */

import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { Skeleton, TableSkeleton, CardSkeleton, ChartSkeleton } from './Skeleton';

describe('Skeleton', () => {
  it('should render skeleton element', () => {
    const { container } = render(<Skeleton />);
    const skeleton = container.querySelector('.animate-pulse');
    expect(skeleton).toBeInTheDocument();
  });

  it('should apply custom className', () => {
    const { container } = render(<Skeleton className="custom-class" />);
    const skeleton = container.querySelector('.custom-class');
    expect(skeleton).toBeInTheDocument();
  });

  it('should render with different sizes', () => {
    const { container: container1 } = render(<Skeleton className="h-4 w-4" />);
    const { container: container2 } = render(<Skeleton className="h-8 w-8" />);

    expect(container1.querySelector('.h-4')).toBeInTheDocument();
    expect(container2.querySelector('.h-8')).toBeInTheDocument();
  });
});

describe('TableSkeleton', () => {
  it('should render table skeleton', () => {
    const { container } = render(<TableSkeleton rows={3} columns={4} />);
    expect(container.querySelector('.space-y-4')).toBeInTheDocument();
  });

  it('should render with default props', () => {
    const { container } = render(<TableSkeleton />);
    expect(container.querySelector('.space-y-4')).toBeInTheDocument();
  });
});

describe('CardSkeleton', () => {
  it('should render card skeleton', () => {
    const { container } = render(<CardSkeleton />);
    expect(container.querySelector('.rounded-lg')).toBeInTheDocument();
  });
});

describe('ChartSkeleton', () => {
  it('should render chart skeleton', () => {
    const { container } = render(<ChartSkeleton />);
    expect(container.querySelector('.rounded-lg')).toBeInTheDocument();
  });

  it('should render with custom height', () => {
    const { container } = render(<ChartSkeleton height={400} />);
    const skeleton = container.querySelector('[style*="height"]');
    expect(skeleton).toBeInTheDocument();
  });
});
