/* eslint-disable max-lines-per-function -- approval queue tests keep governed fixtures local to branch assertions. */
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "@/stores/auth-store";
import type {
  AgentManagementConfiguration,
  ApprovalDetail,
  ApprovalListItem,
  ApprovalDecisionRequest,
  PageResult,
  PaginationMeta,
} from "../contracts";
import { aiAgentService } from "../services/ai-agent-service";
import { ApprovalQueuePage } from "./ApprovalQueuePage";

vi.mock("../services/ai-agent-service", () => ({
  aiAgentService: {
    approveRequest: vi.fn(),
    getConfiguration: vi.fn(),
    listApprovals: vi.fn(),
    rejectRequest: vi.fn(),
  },
}));

const pagination: PaginationMeta = {
  count: 0,
  page: 1,
  page_size: 25,
  total_pages: 1,
  has_next: false,
  has_previous: false,
};

function page(items: readonly ApprovalListItem[]): PageResult<ApprovalListItem> {
  return {
    items,
    pagination: { ...pagination, count: items.length },
    correlationId: "corr-approvals",
    receivedAt: "2026-07-23T00:00:00Z",
  };
}

const configuration = {
  id: "configuration-1",
  environment: "production",
  version: 1,
  document: {
    ui: {
      approval_page_size: 25,
      approval_poll_interval_ms: 0,
      status_tokens: {
        success: "status-success",
        info: "status-info",
        warning: "status-warning",
        danger: "status-danger",
        neutral: "status-neutral",
      },
      status_token_by_state: {
        pending: "warning",
        approved: "success",
        rejected: "danger",
        expired: "neutral",
        cancelled: "neutral",
      },
    },
  },
  created_at: "2026-07-23T00:00:00Z",
  updated_at: "2026-07-23T00:00:00Z",
} as unknown as AgentManagementConfiguration;

const approval: ApprovalListItem = {
  id: "approval-1",
  tool_id: "tool-1",
  tool_name: "Post invoice",
  agent_execution_id: "execution-1",
  requested_by: "requester-1",
  requested_for: "requester-1",
  approver_id: null,
  status: "pending",
  justification: "Needs controlled side effect",
  requested_at: "2026-07-23T00:00:00Z",
  expires_at: "2999-01-01T00:00:00Z",
  decided_at: null,
};

function approvalDetail(status: ApprovalDetail["status"]): ApprovalDetail {
  return {
    ...approval,
    status,
    tool_invocation_id: "invocation-1",
    rejection_reason: status === "rejected" ? "Policy mismatch" : "",
    transition_history: [],
    tool_input: { invoice_id: "invoice-1" },
    sod_warning: null,
    audit_correlation_id: "corr-approval",
  };
}

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="path">{location.pathname}</span>;
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Routes>
          <Route
            path="*"
            element={
              <>
                <ApprovalQueuePage />
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("ApprovalQueuePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    useAuthStore.setState({
      user: {
        id: "approver-1",
        email: "approver@saraise.com",
        username: "approver",
        is_staff: false,
        is_superuser: false,
        tenant_id: "tenant-1",
        platform_role: null,
        tenant_role: "operator",
      },
      isAuthenticated: true,
      isLoading: false,
    });
    vi.mocked(aiAgentService.getConfiguration).mockResolvedValue(configuration);
    vi.mocked(aiAgentService.listApprovals).mockResolvedValue(page([approval]));
    vi.mocked(aiAgentService.approveRequest).mockResolvedValue(approvalDetail("approved"));
    vi.mocked(aiAgentService.rejectRequest).mockResolvedValue(approvalDetail("rejected"));
  });

  it("loads pending approvals with governed page size and navigates to immutable detail evidence", async () => {
    renderPage();

    const link = await screen.findByRole("link", { name: "Post invoice" });
    expect(link).toHaveAttribute("href", "/ai-agents/approvals/approval-1");
    expect(screen.getByText("Needs controlled side effect")).toBeInTheDocument();
    expect(screen.getByText(/remaining/u)).toBeInTheDocument();
    expect(aiAgentService.listApprovals).toHaveBeenCalledWith({
      status: "pending",
      page_size: 25,
    });
  });

  it("filters by decision state and renders a status-specific empty state", async () => {
    const user = userEvent.setup();
    vi.mocked(aiAgentService.listApprovals)
      .mockResolvedValueOnce(page([approval]))
      .mockResolvedValueOnce(page([]));
    renderPage();

    await screen.findByText("Post invoice");
    await user.selectOptions(screen.getByLabelText(/decision state/i), "approved");

    await waitFor(() =>
      expect(aiAgentService.listApprovals).toHaveBeenLastCalledWith({
        status: "approved",
        page_size: 25,
      })
    );
    expect(await screen.findByText("No requests match this decision state.")).toBeInTheDocument();
  });

  it("blocks self-approval and expired requests without rendering decision controls", async () => {
    const selfApproval = { ...approval, id: "approval-self", requested_by: "approver-1" };
    const expiredApproval = {
      ...approval,
      id: "approval-expired",
      tool_name: "Expire session",
      expires_at: "2000-01-01T00:00:00Z",
    };
    vi.mocked(aiAgentService.listApprovals).mockResolvedValue(
      page([selfApproval, expiredApproval])
    );

    renderPage();

    expect(
      await screen.findByText("Separation of duties: you cannot decide your own request.")
    ).toBeInTheDocument();
    const expiredRow = screen.getByText("Expire session").closest("li");
    if (!expiredRow) throw new Error("Expired approval row did not render.");
    expect(within(expiredRow).getByText("Expired")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
  });

  it("requires a rejection reason and sends transition payloads for decisions", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Post invoice");
    const reject = screen.getByRole("button", { name: "Reject" });
    expect(reject).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(aiAgentService.approveRequest).toHaveBeenCalled());
    const approveCall = vi.mocked(aiAgentService.approveRequest).mock.calls.at(-1) as
      | [string, ApprovalDecisionRequest]
      | undefined;
    expect(approveCall?.[0]).toBe("approval-1");
    expect(approveCall?.[1].transition_key).toMatch(/^approve-/u);

    vi.mocked(aiAgentService.listApprovals).mockResolvedValue(page([approval]));
    await user.selectOptions(screen.getByLabelText(/decision state/i), "");
    await screen.findByText("Post invoice");
    await user.type(screen.getByLabelText("Rejection reason for approval-1"), "Policy mismatch");
    await user.click(screen.getByRole("button", { name: "Reject" }));

    await waitFor(() => expect(aiAgentService.rejectRequest).toHaveBeenCalled());
    const rejectCall = vi.mocked(aiAgentService.rejectRequest).mock.calls.at(-1) as
      | [string, ApprovalDecisionRequest]
      | undefined;
    expect(rejectCall?.[0]).toBe("approval-1");
    expect(rejectCall?.[1].reason).toBe("Policy mismatch");
    expect(rejectCall?.[1].transition_key).toMatch(/^reject-/u);
  });

  it("restores optimistically removed rows and shows mutation errors when approval fails", async () => {
    const user = userEvent.setup();
    vi.mocked(aiAgentService.approveRequest).mockRejectedValue(new Error("approval conflict"));
    renderPage();

    await screen.findByText("Post invoice");
    await user.click(screen.getByRole("button", { name: "Approve" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("approval conflict");
    expect(screen.getByText("Post invoice")).toBeInTheDocument();
  });

  it("renders retryable configuration and approval load failures", async () => {
    const user = userEvent.setup();
    vi.mocked(aiAgentService.getConfiguration)
      .mockRejectedValueOnce(new Error("configuration unavailable"))
      .mockResolvedValueOnce(configuration);
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("configuration unavailable");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByText("Post invoice");

    vi.clearAllMocks();
    vi.mocked(aiAgentService.getConfiguration).mockResolvedValue(configuration);
    vi.mocked(aiAgentService.listApprovals)
      .mockRejectedValueOnce(new Error("approval list unavailable"))
      .mockResolvedValueOnce(page([]));
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("approval list unavailable");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No requests match this decision state.")).toBeInTheDocument();
  });
});
