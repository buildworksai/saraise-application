/* eslint-disable max-lines-per-function -- cohesive UI primitive branch coverage keeps fixtures local. */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  ApiProblem,
  Breadcrumbs,
  EmptyPanel,
  MutationProblem,
  PageHeader,
  PageSkeleton,
  Pagination,
  RefreshStatus,
  can,
  formatBytes,
  formatDate,
  saveDownload,
  useUnsavedChanges,
} from "./DmsUI";
import { DmsApiError } from "../services/dms-service";
import type { Folder } from "../contracts";

describe("DMS governed UI states", () => {
  afterEach(() => vi.restoreAllMocks());

  it.each([
    [
      { kind: "denied", status: 403, message: "hidden", correlation_id: "corr-denied" } as const,
      "Access denied",
    ],
    [
      {
        kind: "not_found",
        status: 404,
        message: "hidden",
        correlation_id: "corr-not-found",
      } as const,
      "Document unavailable",
    ],
    [
      {
        kind: "unavailable",
        status: 503,
        message: "offline",
        correlation_id: "corr-storage",
      } as const,
      "Document storage unavailable",
    ],
    [
      { kind: "conflict", status: 409, message: "stale", correlation_id: "corr-conflict" } as const,
      "A newer revision exists",
    ],
  ])("renders a safe recovery state for %s", (problem, title) => {
    render(<ApiProblem error={new DmsApiError(problem)} />);
    expect(screen.getByRole("alert")).toHaveTextContent(title);
    expect(screen.getByText(new RegExp(problem.correlation_id, "u"))).toBeInTheDocument();
    expect(screen.queryByText(problem.message)).not.toBeInTheDocument();
  });

  it("distinguishes empty folders from filtered-empty results", () => {
    const { rerender } = render(<EmptyPanel filtered={false} folder />);
    expect(screen.getByText("This folder is empty")).toBeInTheDocument();
    rerender(<EmptyPanel filtered folder={false} onReset={() => undefined} />);
    expect(screen.getByText("No documents match these filters")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear filters" })).toBeEnabled();
    rerender(
      <EmptyPanel filtered={false} folder={false} action={<button>Upload document</button>} />
    );
    expect(screen.getByText("No documents yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload document" })).toBeEnabled();
  });

  it("maps backend ACL capabilities to precise UI actions", () => {
    expect(can(["write"], "update")).toBe(true);
    expect(can(["write"], "move")).toBe(true);
    expect(can(["write"], "create_version")).toBe(true);
    expect(can(["manage"], "restore_version")).toBe(true);
    expect(can(["manage"], "manage_permissions")).toBe(true);
    expect(can(["read"], "manage_permissions")).toBe(false);
    expect(can(["read"], "delete")).toBe(false);
    expect(can(["download"], "download")).toBe(true);
    expect(can(["create"], "share")).toBe(false);
  });

  it("renders loading, refresh, headers, and retry affordances without layout loss", async () => {
    const retry = vi.fn();
    render(
      <>
        <PageHeader
          title="Documents"
          description="Governed records"
          actions={<button>New</button>}
        />
        <PageSkeleton rows={2} label="Loading DMS records" />
        <RefreshStatus active />
        <ApiProblem error={new Error("Network failed")} onRetry={retry} />
      </>
    );
    expect(screen.getByRole("heading", { name: "Documents" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New" })).toBeEnabled();
    expect(screen.getByLabelText("Loading DMS records")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("status")).toHaveTextContent("Refreshing documents");
    expect(screen.getByRole("alert")).toHaveTextContent("Document request failed");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("formats governed date and byte values at documented boundaries", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate(undefined)).toBe("—");
    expect(formatDate("2026-07-22T00:00:00Z")).toContain("2026");
    expect(formatBytes(undefined)).toBe("—");
    expect(formatBytes(1023)).toBe("1023 B");
    expect(formatBytes(1024)).toBe("1.0 KiB");
    expect(formatBytes(1024 ** 2)).toBe("1.0 MiB");
  });

  it("saves downloads through an object URL and revokes it", () => {
    const click = vi.fn();
    const originalCreateElement = document.createElement.bind(document);
    const originalCreateObjectURL = Object.getOwnPropertyDescriptor(URL, "createObjectURL");
    const originalRevokeObjectURL = Object.getOwnPropertyDescriptor(URL, "revokeObjectURL");
    const anchor = originalCreateElement("a");
    const createObjectURL = vi.fn(() => "blob:download");
    const revokeObjectURL = vi.fn();
    anchor.click = click;
    vi.spyOn(document, "createElement").mockImplementation((tagName) =>
      tagName === "a" ? anchor : originalCreateElement(tagName)
    );
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL });
    try {
      saveDownload({
        blob: new Blob(["content"]),
        filename: "policy.pdf",
        mime_type: "application/pdf",
      });
    } finally {
      if (originalCreateObjectURL)
        Object.defineProperty(URL, "createObjectURL", originalCreateObjectURL);
      else Reflect.deleteProperty(URL, "createObjectURL");
      if (originalRevokeObjectURL)
        Object.defineProperty(URL, "revokeObjectURL", originalRevokeObjectURL);
      else Reflect.deleteProperty(URL, "revokeObjectURL");
    }

    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(anchor.href).toBe("blob:download");
    expect(anchor.download).toBe("policy.pdf");
    expect(click).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:download");
  });

  it("guards dirty pages with beforeunload and removes the listener on cleanup", () => {
    function DirtyHarness({ dirty }: { readonly dirty: boolean }) {
      useUnsavedChanges(dirty);
      return <span>dirty harness</span>;
    }
    const { rerender, unmount } = render(<DirtyHarness dirty />);
    const dirtyEvent = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirtyEvent);
    expect(dirtyEvent.defaultPrevented).toBe(true);

    rerender(<DirtyHarness dirty={false} />);
    const cleanEvent = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(cleanEvent);
    expect(cleanEvent.defaultPrevented).toBe(false);
    unmount();
    const unmountedEvent = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(unmountedEvent);
    expect(unmountedEvent.defaultPrevented).toBe(false);
  });

  it("renders validation field failures only when supplied by the governed error", () => {
    const error = new DmsApiError({
      kind: "validation",
      status: 422,
      message: "Invalid document",
      field_errors: [{ field: "name", code: "required", message: "Name is required" }],
      correlation_id: "corr-validation",
    });
    const { rerender } = render(<MutationProblem error={error} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Invalid document");
    expect(screen.getByText("name: Name is required")).toBeInTheDocument();
    rerender(<MutationProblem error={new Error("Plain failure")} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Plain failure");
    expect(screen.queryByText("name: Name is required")).not.toBeInTheDocument();
  });

  it("keeps pagination and breadcrumb actions exact at collection boundaries", async () => {
    const page = vi.fn();
    const root = vi.fn();
    const folder: Folder = {
      id: "folder-1",
      name: "Legal",
      description: "",
      parent_id: null,
      path: "/Legal",
      depth: 0,
      sort_order: 0,
      created_by: "actor-1",
      created_at: "2026-07-22T00:00:00Z",
      updated_at: "2026-07-22T00:00:00Z",
      allowed_actions: ["read"],
    };
    const { rerender } = render(
      <>
        <Pagination
          value={{
            count: 50,
            page: 2,
            page_size: 25,
            total_pages: 2,
            has_next: false,
            has_previous: true,
          }}
          onPage={page}
        />
        <Breadcrumbs folders={[folder]} onRoot={root} />
      </>
    );
    expect(screen.getByText("Page 2 of 2 · 50 documents")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    await userEvent.click(screen.getByRole("button", { name: "Documents" }));
    expect(page).toHaveBeenCalledWith(1);
    expect(root).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();

    rerender(
      <Pagination
        value={{
          count: 0,
          page: 1,
          page_size: 25,
          total_pages: 0,
          has_next: true,
          has_previous: false,
        }}
        onPage={page}
      />
    );
    expect(screen.getByText("Page 1 of 1 · 0 documents")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(page).toHaveBeenLastCalledWith(2);
  });
});
