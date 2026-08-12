import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as RouterDom from "react-router-dom";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { notificationService } from "@/modules/notifications/services/notification-service";
import { NotificationBell } from "./NotificationBell";

const navigateSpy = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof RouterDom>("react-router-dom");
  return { ...actual, useNavigate: () => navigateSpy };
});

vi.mock("@/modules/notifications/services/notification-service", () => ({
  notificationService: {
    getUnreadCount: vi.fn(),
  },
}));

function renderBell() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <NotificationBell />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("NotificationBell", () => {
  beforeEach(() => {
    navigateSpy.mockClear();
    vi.mocked(notificationService.getUnreadCount).mockReset();
  });

  it("renders a capped unread count and routes to the notification center", async () => {
    const user = userEvent.setup();
    vi.mocked(notificationService.getUnreadCount).mockResolvedValue(120);

    renderBell();

    expect(await screen.findByText("99+")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Notifications" }));
    expect(navigateSpy).toHaveBeenCalledWith("/notifications");
  });

  it("omits the badge when there are no unread notifications", async () => {
    vi.mocked(notificationService.getUnreadCount).mockResolvedValue(0);

    renderBell();

    await waitFor(() => expect(notificationService.getUnreadCount).toHaveBeenCalled());
    expect(screen.queryByText("0")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Notifications" })).toBeInTheDocument();
  });
});
