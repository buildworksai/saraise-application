import type { ReactNode } from "react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

const renderMock = vi.fn();
const createRootMock = vi.fn(() => ({ render: renderMock }));

vi.mock("react-dom/client", () => {
  return {
    default: {
      createRoot: createRootMock,
    },
    createRoot: createRootMock,
  };
});
vi.mock("./App", () => ({ default: () => <div data-testid="app" /> }));
vi.mock("./lib/theme-provider", () => ({
  ThemeProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));
vi.mock("sonner", () => ({ Toaster: () => null }));

describe("main bootstrap", () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="root"></div>';
    createRootMock.mockClear();
    renderMock.mockClear();
  });

  afterEach(() => {
    vi.resetModules();
  });

  it("mounts the React app into #root", async () => {
    await import("./main");

    const rootEl = document.getElementById("root");
    expect(rootEl).not.toBeNull();

    expect(createRootMock).toHaveBeenCalledTimes(1);
    expect(createRootMock).toHaveBeenCalledWith(rootEl);
    expect(renderMock).toHaveBeenCalledTimes(1);
  });
});
