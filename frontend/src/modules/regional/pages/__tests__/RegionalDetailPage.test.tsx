import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RegionalDetailPage } from "../RegionalDetailPage";
import { regionalService } from "../../services/regional-service";
import { ROUTES } from "../../contracts";
import { configurationFixture, resourceFixture } from "./regional-test-fixtures";

vi.mock("../../services/regional-service");
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/regional/test-id"]}>
        <Routes>
          <Route path={ROUTES.DETAIL_PATTERN} element={<RegionalDetailPage />} />
          <Route path="*" element={<div>navigated</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("RegionalDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(regionalService.getActiveConfiguration).mockResolvedValue(configurationFixture());
  });

  it("renders a complete typed resource", async () => {
    vi.mocked(regionalService.getResource).mockResolvedValue(
      resourceFixture({ id: "test-id", name: "Test resource" })
    );
    renderPage();
    expect(await screen.findByText("Test resource")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("distinguishes a request failure and provides retry", async () => {
    vi.mocked(regionalService.getResource).mockRejectedValue(new Error("Service unavailable"));
    renderPage();
    expect(await screen.findByText("Unable to load resource")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try Again" })).toBeInTheDocument();
  });

  it("uses active configuration to execute governed lifecycle transitions", async () => {
    vi.mocked(regionalService.getResource).mockResolvedValue(
      resourceFixture({ id: "test-id", name: "Inactive region", is_active: false })
    );
    vi.mocked(regionalService.activateResource).mockResolvedValue(
      resourceFixture({ id: "test-id", name: "Inactive region", is_active: true })
    );

    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Activate" }));

    await waitFor(() => expect(regionalService.activateResource).toHaveBeenCalledWith("test-id"));
    expect(regionalService.deactivateResource).not.toHaveBeenCalled();
  });

  it("requires configured archive confirmation before deleting and navigating away", async () => {
    vi.mocked(regionalService.getResource).mockResolvedValue(
      resourceFixture({ id: "test-id", name: "Archivable region" })
    );
    vi.mocked(regionalService.deleteResource).mockResolvedValue(undefined);

    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Archive" }));
    expect(regionalService.deleteResource).not.toHaveBeenCalled();
    expect(
      await screen.findByRole("dialog", { name: "Archive this resource?" })
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Archive resource" }));

    await waitFor(() => expect(regionalService.deleteResource).toHaveBeenCalledWith("test-id"));
    expect(await screen.findByText("navigated")).toBeInTheDocument();
  });
});
