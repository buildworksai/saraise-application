import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/api-client";
import { AccessSimulatorPage } from "./AccessSimulatorPage";
import { RoleCreatePage, RolesPage } from "./RolesPage";

const mocks = vi.hoisted(() => ({ listRoles: vi.fn(), createRole: vi.fn(), simulate: vi.fn() }));
vi.mock("../services/security-service", () => ({ securityService: { roles: { list: mocks.listRoles, create: mocks.createRole }, accessDecisions: { simulate: mocks.simulate } } }));

const pagination = { count: 0, page: 1, page_size: 25, total_pages: 0, has_next: false, has_previous: false };
const empty = { items: [], pagination, correlationId: "corr-list", timestamp: "2026-07-22T00:00:00Z" };
function renderPage(page: React.ReactNode, initial = "/security-access-control/roles") { const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } }); return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[initial]}>{page}</MemoryRouter></QueryClientProvider>); }

describe("security administration page states", () => {
  beforeEach(() => vi.clearAllMocks());
  it("renders an initial list skeleton", () => { mocks.listRoles.mockReturnValue(new Promise(() => undefined)); renderPage(<RolesPage/>); expect(screen.getByLabelText("Loading security administration data")).toHaveAttribute("aria-busy", "true"); });
  it("distinguishes unfiltered and filtered empty states", async () => { mocks.listRoles.mockResolvedValue(empty); const first = renderPage(<RolesPage/>); expect(await screen.findByText("No roles yet")).toBeInTheDocument(); first.unmount(); renderPage(<RolesPage/>, "/security-access-control/roles?search=missing"); expect(await screen.findByText("No roles match these filters")).toBeInTheDocument(); expect(screen.getByRole("button", { name: "Reset filters" })).toBeInTheDocument(); });
  it("surfaces governed correlation IDs and retry", async () => { mocks.listRoles.mockRejectedValue(new ApiError("Denied", 403, undefined, "POLICY_DENIED", "corr-denied")); renderPage(<RolesPage/>); expect(await screen.findByText("Access denied")).toBeInTheDocument(); expect(screen.getByText(/corr-denied/u)).toBeInTheDocument(); await userEvent.click(screen.getByRole("button", { name: "Retry" })); expect(mocks.listRoles).toHaveBeenCalledTimes(2); });
  it("renders successful role data and loads the next bounded page", async () => { mocks.listRoles.mockResolvedValue({ items: [{ id: "role-1", name: "Support", code: "support", description: "Support access", role_type: "functional", hierarchy_level: 0, is_active: true }], pagination: { ...pagination, count: 26, total_pages: 2, has_next: true }, correlationId: "corr-list", timestamp: "2026-07-22T00:00:00Z" }); renderPage(<RolesPage/>); expect(await screen.findByText("Support")).toBeInTheDocument(); await userEvent.click(screen.getByRole("button", { name: /Next/u })); await waitFor(() => expect(mocks.listRoles).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2, page_size: 25 }))); });
  it("validates create fields before submitting", async () => { mocks.listRoles.mockResolvedValue(empty); renderPage(<RoleCreatePage/>, "/security-access-control/roles/create"); await userEvent.type(screen.getByLabelText("Name"), "A"); await userEvent.type(screen.getByLabelText("Stable code"), "A"); await userEvent.click(screen.getByRole("button", { name: "Save role" })); expect(mocks.createRole).not.toHaveBeenCalled(); expect(await screen.findByText(/at least 2 character/u)).toBeInTheDocument(); });
  it("explains an authoritative simulation result", async () => { mocks.simulate.mockResolvedValue({ data: { subject_id: "00000000-0000-0000-0000-000000000001", permission_code: "security.roles:read", decision: "deny", reason_codes: ["NO_MATCHING_GRANT"], applied_policy_ids: [], entitlement: { required: false, allowed: true }, quota: { required: false, allowed: true }, field_decisions: [], row_explanation: null, audit_log_id: null, correlation_id: "corr-sim", evaluated_at: "2026-07-22T00:00:00Z" }, correlationId: "corr-sim", timestamp: "2026-07-22T00:00:00Z" }); renderPage(<AccessSimulatorPage/>, "/security-access-control/access-simulator"); await userEvent.type(screen.getByLabelText("Subject UUID"), "00000000-0000-0000-0000-000000000001"); await userEvent.type(screen.getByLabelText("Permission code"), "security.roles:read"); await userEvent.click(screen.getByRole("button", { name: "Explain access" })); expect(await screen.findByText("Access denied")).toBeInTheDocument(); expect(screen.getByText("NO_MATCHING_GRANT")).toBeInTheDocument(); expect(screen.getByText(/corr-sim/u)).toBeInTheDocument(); });
});
