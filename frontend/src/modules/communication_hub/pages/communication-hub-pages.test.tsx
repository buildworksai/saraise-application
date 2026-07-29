import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChannelListPage } from "./ChannelListPage";
import { ConfigurationPage } from "./ConfigurationPage";
import { MessageListPage } from "./MessageListPage";
import { TemplatesPage } from "./TemplatesPage";
import { communicationHubService } from "../services/communication-hub-service";

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("communication hub pages", () => {
  it("renders channels from the backend service", async () => {
    vi.spyOn(communicationHubService, "listChannels").mockResolvedValue([
      {
        id: "channel-1",
        tenant_id: "tenant-1",
        channel_code: "EMAIL",
        channel_name: "Email",
        channel_type: "email",
        is_active: true,
        created_at: "2026-07-29T00:00:00Z",
        updated_at: "2026-07-29T00:00:00Z",
      },
    ]);
    renderWithQuery(<ChannelListPage />);
    await waitFor(() => expect(screen.getByText("Communication channels")).toBeInTheDocument());
    expect(screen.getByText("EMAIL")).toBeInTheDocument();
    expect(screen.getByText("Email")).toBeInTheDocument();
  });

  it("renders messages from the backend service", async () => {
    vi.spyOn(communicationHubService, "listMessages").mockResolvedValue([
      {
        id: "message-1",
        tenant_id: "tenant-1",
        channel: "channel-1",
        channel_code: "EMAIL",
        channel_name: "Email",
        sender_id: "00000000-0000-0000-0000-000000000001",
        recipient_id: null,
        subject: "Tenant notice",
        body: "Body",
        message_type: "email",
        status: "sent",
        created_at: "2026-07-29T00:00:00Z",
        updated_at: "2026-07-29T00:00:00Z",
      },
    ]);
    renderWithQuery(<MessageListPage />);
    await waitFor(() => expect(screen.getByText("Communication messages")).toBeInTheDocument());
    expect(screen.getByText("Tenant notice")).toBeInTheDocument();
    expect(screen.getByText("sent")).toBeInTheDocument();
  });

  it("documents missing template and configuration backend contracts without mock data", () => {
    render(<TemplatesPage />);
    expect(screen.getByText("Communication templates")).toBeInTheDocument();
    expect(screen.getByText(/No template API exists/u)).toBeInTheDocument();

    render(<ConfigurationPage />);
    expect(screen.getByText("Communication configuration")).toBeInTheDocument();
    expect(
      screen.getByText(
        /no configuration read, preview, version, import, export, or rollback endpoints/u
      )
    ).toBeInTheDocument();
  });
});
