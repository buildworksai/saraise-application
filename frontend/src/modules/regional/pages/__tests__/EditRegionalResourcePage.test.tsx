import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ROUTES } from "../../contracts";
import { regionalService } from "../../services/regional-service";
import { EditRegionalResourcePage } from "../EditRegionalResourcePage";
import { configurationFixture, resourceFixture } from "./regional-test-fixtures";

vi.mock("../../services/regional-service");
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="Current route">{location.pathname}</output>;
}

function renderPage(path = "/regional/resource-1/edit") {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
        })
      }
    >
      <MemoryRouter initialEntries={[path]}>
        <LocationProbe />
        <Routes>
          <Route path={ROUTES.EDIT_PATTERN} element={<EditRegionalResourcePage />} />
          <Route path={ROUTES.DETAIL_PATTERN} element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("EditRegionalResourcePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    const configuration = configurationFixture();
    vi.mocked(regionalService.getActiveConfiguration).mockResolvedValue({
      ...configuration,
      document: {
        ...configuration.document,
        resource: {
          ...configuration.document.resource,
          name_min_length: 3,
          name_max_length: 40,
          description_max_length: 80,
        },
      },
    });
    vi.mocked(regionalService.getResource).mockResolvedValue(
      resourceFixture({ id: "resource-1", name: "India GST" })
    );
  });

  it("validates governed field limits before submitting an update payload", async () => {
    const user = userEvent.setup();
    renderPage();

    const name = await screen.findByLabelText("Name");
    await user.clear(name);
    await user.type(name, "  ");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Name must contain at least 3 characters")).toBeInTheDocument();
    expect(regionalService.updateResource).not.toHaveBeenCalled();

    await user.clear(name);
    await user.type(name, "India GST 2026");
    await user.clear(screen.getByLabelText("Description"));
    await user.type(screen.getByLabelText("Description"), "Updated regional compliance scope");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(regionalService.updateResource).toHaveBeenCalledWith("resource-1", {
        name: "India GST 2026",
        description: "Updated regional compliance scope",
      })
    );
    expect(screen.getByLabelText("Current route")).toHaveTextContent("/regional/resource-1");
  });

  it("fails closed when either resource or active configuration cannot be loaded", async () => {
    vi.mocked(regionalService.getActiveConfiguration).mockRejectedValueOnce(
      new Error("configuration unavailable")
    );
    renderPage();

    expect(
      await screen.findByText("The resource or its governed configuration could not be loaded.")
    ).toBeInTheDocument();
    expect(regionalService.updateResource).not.toHaveBeenCalled();
  });
});
