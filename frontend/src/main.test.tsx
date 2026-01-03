import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

const renderMock = vi.fn();
const createRootMock = vi.fn(() => ({ render: renderMock }));

vi.mock('react-dom/client', () => {
  return {
    default: {
      createRoot: createRootMock,
    },
    createRoot: createRootMock,
  };
});

describe('main bootstrap', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="root"></div>';
    createRootMock.mockClear();
    renderMock.mockClear();
  });

  afterEach(() => {
    vi.resetModules();
  });

  it('mounts the React app into #root', async () => {
    await import('./main');

    const rootEl = document.getElementById('root');
    expect(rootEl).not.toBeNull();

    expect(createRootMock).toHaveBeenCalledTimes(1);
    expect(createRootMock).toHaveBeenCalledWith(rootEl);
    expect(renderMock).toHaveBeenCalledTimes(1);
  });
});
