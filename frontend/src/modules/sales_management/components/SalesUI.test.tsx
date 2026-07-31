/* eslint-disable @typescript-eslint/unbound-method, max-lines-per-function -- tests assert query-result callbacks and router behavior across broad shared UI states. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/api-client";
import type { ApiV2Page, Customer, TransitionRecord } from "../contracts";
import {
  DetailGrid,
  GovernedError,
  ResourceList,
  StatusPill,
  Timeline,
  useListFilters,
  useUnsavedChanges,
} from "./SalesUi";

const page = <T,>(data: T[], overrides: Partial<ApiV2Page<T>["meta"]["pagination"]> = {}) => ({
  data,
  meta: {
    correlation_id: "corr-sales-ui",
    timestamp: "2026-07-31T00:00:00Z",
    pagination: {
      page: 1,
      page_size: 25,
      count: data.length,
      total_pages: 1,
      has_next: false,
      has_previous: false,
      ...overrides,
    },
  },
});

const customer: Customer = {
  id: "customer-1",
  tenant_id: "tenant-1",
  customer_code: "ACME",
  customer_name: "ACME Industries",
  email: "buyer@example.com",
  phone: "555-0100",
  address: "1 Main Street",
  credit_limit: "1000.00",
  currency: "USD",
  is_active: true,
  created_at: "2026-07-31T00:00:00Z",
  updated_at: "2026-07-31T00:00:00Z",
  created_by: "user-1",
  updated_by: "user-1",
  deleted_at: null,
  deleted_by: null,
  lock_version: 1,
};

function renderWithRouter(element: React.ReactElement, entry = "/sales-management/customers") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/sales-management/customers" element={element} />
          <Route path="/sales-management/customers/:id" element={<p>Customer detail</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function SalesFiltersProbe() {
  const filters = useListFilters();
  return <pre>{JSON.stringify(filters)}</pre>;
}

function UnsavedProbe({ dirty }: { dirty: boolean }) {
  useUnsavedChanges(dirty);
  return <p>dirty={String(dirty)}</p>;
}

describe("sales shared UI primitives", () => {
  it("renders list loading, error, empty, filtering, pagination, and row navigation states", async () => {
    const refetch = vi.fn().mockResolvedValue(undefined);

    const queryResult: {
      data?: ApiV2Page<Customer>;
      isLoading: boolean;
      isFetching: boolean;
      error: unknown;
      refetch: () => Promise<unknown>;
    } = {
      data: undefined,
      isLoading: true,
      isFetching: false,
      error: null,
      refetch,
    };
    const columns = [
      { key: "code", label: "Code", render: (row: Customer) => row.customer_code },
      { key: "name", label: "Name", render: (row: Customer) => row.customer_name },
    ];
    const list = (overrides: Partial<typeof queryResult>) => (
      <ResourceList
        title="Customers"
        description="Tenant profiles"
        createLabel="Create customer"
        createPath="/sales-management/customers/new"
        detailPath={(id) => `/sales-management/customers/${id}`}
        queryResult={{ ...queryResult, ...overrides }}
        columns={columns}
        emptyTitle="No customers yet"
        searchPlaceholder="Search customers"
        orderingOptions={[{ value: "customer_code", label: "Code A-Z" }]}
        filterOptions={[
          {
            key: "is_active",
            label: "Status",
            options: [{ value: "true", label: "Active" }],
          },
        ]}
      />
    );

    const { rerender } = renderWithRouter(list({}));
    expect(screen.getByLabelText("Loading customers")).toBeInTheDocument();

    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={["/sales-management/customers"]}>
          {list({ isLoading: false, error: new ApiError("Denied", 403, undefined, "FORBIDDEN", "corr-denied") })}
        </MemoryRouter>
      </QueryClientProvider>
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Access denied");
    expect(screen.getByRole("alert")).toHaveTextContent("corr-denied");
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(refetch).toHaveBeenCalled();

    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={["/sales-management/customers"]}>
          {list({ isLoading: false, data: page([]) })}
        </MemoryRouter>
      </QueryClientProvider>
    );
    expect(screen.getByText("No customers yet")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Create customer" })).toHaveLength(2);

    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={["/sales-management/customers"]}>
          {list({
            isLoading: false,
            isFetching: true,
            data: page([customer], { page: 1, total_pages: 2, has_next: true }),
          })}
        </MemoryRouter>
      </QueryClientProvider>
    );
    expect(screen.getByText("ACME Industries")).toBeInTheDocument();
    expect(screen.getByText("Refreshing…")).toBeInTheDocument();
    await userEvent.type(screen.getByPlaceholderText("Search customers"), "ACME");
    await userEvent.selectOptions(screen.getByLabelText("Status"), "true");
    await userEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(screen.getByRole("link", { name: "View" })).toHaveAttribute(
      "href",
      "/sales-management/customers/customer-1"
    );
  });

  it("formats status, detail fallback, timeline evidence, list filters, and unload protection", () => {
    const transition: TransitionRecord = {
      command: "send",
      from_status: "draft",
      to_status: "sent",
      actor_id: "user-1",
      correlation_id: "corr-transition",
      occurred_at: "2026-07-31T00:00:00Z",
      reason: "Customer requested quote",
    };
    const { rerender } = renderWithRouter(
      <>
        <StatusPill status="ready_to_ship" />
        <DetailGrid entries={[["Tracking", ""], ["Currency", "USD"]]} />
        <Timeline records={[transition]} />
        <SalesFiltersProbe />
        <UnsavedProbe dirty={false} />
      </>,
      "/sales-management/customers?page=3&page_size=50&is_active=true&search=ACME"
    );

    expect(screen.getByText("ready to ship")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText("draft → sent")).toBeInTheDocument();
    expect(screen.getByText(/"page":3/u)).toBeInTheDocument();
    expect(screen.getByText(/"is_active":true/u)).toBeInTheDocument();

    const prevented = vi.fn();
    fireEvent(
      window,
      new Event("beforeunload", { cancelable: true, bubbles: true })
    );
    expect(prevented).not.toHaveBeenCalled();

    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={["/sales-management/customers"]}>
          <UnsavedProbe dirty />
        </MemoryRouter>
      </QueryClientProvider>
    );
    const event = new Event("beforeunload", { cancelable: true });
    const preventSpy = vi.spyOn(event, "preventDefault");
    window.dispatchEvent(event);
    expect(preventSpy).toHaveBeenCalled();
  });

  it("maps governed errors to operator-facing titles", () => {
    const statuses = [
      [404, "Record not found"],
      [409, "This record changed"],
      [503, "Capability unavailable"],
      [500, "Sales data unavailable"],
    ] as const;
    for (const [status, title] of statuses) {
      const { unmount } = renderWithRouter(
        <GovernedError error={new ApiError("Failure", status)} />
      );
      expect(screen.getByText(title)).toBeInTheDocument();
      unmount();
    }
  });
});
