import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ModuleHealth } from "../contracts";
import { documentIntelligenceConfigurationKey } from "../hooks/use-document-intelligence-configuration";
import {
  DocumentIntelligenceApiError,
  documentIntelligenceService,
} from "../services/document-intelligence-service";
import { documentIntelligenceConfiguration, timestamp } from "./test-fixtures";
import { HealthStatusPage } from "./HealthStatusPage";

function renderHealth() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  client.setQueryData(documentIntelligenceConfigurationKey, documentIntelligenceConfiguration);
  return render(
    <QueryClientProvider client={client}>
      <HealthStatusPage />
    </QueryClientProvider>
  );
}

describe("HealthStatusPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders degraded dependency and circuit state evidence from the governed endpoint", async () => {
    const health: ModuleHealth = {
      status: "degraded",
      live: true,
      ready: false,
      checked_at: timestamp,
      dependencies: [
        {
          name: "providers",
          status: "unavailable",
          code: "provider.circuit_open",
          checked_at: timestamp,
          circuit_state: "open",
        },
        {
          name: "async_execution",
          status: "healthy",
          code: "async.ready",
          checked_at: timestamp,
          circuit_state: "closed",
        },
      ],
    };
    const getHealth = vi.spyOn(documentIntelligenceService, "getHealth").mockResolvedValue(health);

    renderHealth();

    expect(
      await screen.findByRole("heading", { name: "Document intelligence health" })
    ).toBeInTheDocument();
    expect(screen.getByText("degraded")).toBeInTheDocument();
    expect(screen.getByText(/Live: yes/u)).toHaveTextContent("Ready: no");
    expect(screen.getByText("providers")).toBeInTheDocument();
    expect(screen.getByText("provider.circuit_open")).toBeInTheDocument();
    expect(screen.getByText(/Circuit: open/u)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Retry checks" }));
    await waitFor(() => expect(getHealth).toHaveBeenCalledTimes(2));
  });

  it("fails closed with correlation evidence and retry when health cannot be fetched", async () => {
    const getHealth = vi
      .spyOn(documentIntelligenceService, "getHealth")
      .mockRejectedValueOnce(
        new DocumentIntelligenceApiError(
          "Health dependency unavailable",
          503,
          "health_unavailable",
          "corr-health-503",
          {}
        )
      )
      .mockResolvedValueOnce({
        status: "healthy",
        live: true,
        ready: true,
        checked_at: timestamp,
        dependencies: [],
      });

    renderHealth();

    expect(await screen.findByRole("alert")).toHaveTextContent("Health dependency unavailable");
    expect(screen.getByText(/corr-health-503/u)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(getHealth).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("healthy")).toBeInTheDocument();
  });
});
