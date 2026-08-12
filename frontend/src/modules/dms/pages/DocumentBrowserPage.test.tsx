/* eslint-disable max-lines-per-function -- page behavior coverage keeps service fixtures and routing assertions local. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "@/stores/auth-store";
import {
  dmsConfiguration,
  dmsPagination,
  dmsUser,
  documentFixture,
  folderFixture,
} from "../__tests__/fixtures";
import { dmsService } from "../services/dms-service";
import { DocumentBrowserPage } from "./DocumentBrowserPage";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="Current route">{`${location.pathname}${location.search}`}</output>;
}

function renderPage(route = "/dms/documents") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <LocationProbe />
        <Routes>
          <Route path="*" element={<DocumentBrowserPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function mockDownloadUrl() {
  const originalCreateElement = document.createElement.bind(document);
  const originalCreateObjectURL = Object.getOwnPropertyDescriptor(URL, "createObjectURL");
  const originalRevokeObjectURL = Object.getOwnPropertyDescriptor(URL, "revokeObjectURL");
  const anchor = originalCreateElement("a");
  const createObjectURL = vi.fn(() => "blob:dms-download");
  const revokeObjectURL = vi.fn();
  anchor.click = vi.fn();
  vi.spyOn(document, "createElement").mockImplementation((tagName) =>
    tagName === "a" ? anchor : originalCreateElement(tagName)
  );
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL });
  return {
    createObjectURL,
    revokeObjectURL,
    restore: () => {
      if (originalCreateObjectURL)
        Object.defineProperty(URL, "createObjectURL", originalCreateObjectURL);
      else Reflect.deleteProperty(URL, "createObjectURL");
      if (originalRevokeObjectURL)
        Object.defineProperty(URL, "revokeObjectURL", originalRevokeObjectURL);
      else Reflect.deleteProperty(URL, "revokeObjectURL");
    },
  };
}

describe("DocumentBrowserPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    useAuthStore.getState().logout();
  });

  it("hydrates filters from URL configuration and clears selection when filters change", async () => {
    useAuthStore.setState({ user: dmsUser, isAuthenticated: true, isLoading: false });
    vi.spyOn(dmsService, "getConfiguration").mockResolvedValue(dmsConfiguration());
    vi.spyOn(dmsService, "listFolders").mockResolvedValue({
      items: [folderFixture],
      pagination: dmsPagination,
      correlation_id: "corr-folders",
    });
    vi.spyOn(dmsService, "getFolder").mockResolvedValue(folderFixture);
    const listDocuments = vi.spyOn(dmsService, "listDocuments").mockResolvedValue({
      items: [documentFixture],
      pagination: dmsPagination,
      correlation_id: "corr-documents",
    });
    vi.spyOn(dmsService, "downloadDocument").mockResolvedValue({
      blob: new Blob(["content"], { type: "application/pdf" }),
      filename: "retention-policy.pdf",
      mime_type: "application/pdf",
    });

    renderPage(
      "/dms/documents?folder=folder-1&search=retention&mime_type=application/pdf&tag=policy&modified_from=2026-07-01&created_by=actor-1&ordering=invalid"
    );

    expect(await screen.findByRole("heading", { name: "Policies" })).toBeInTheDocument();
    expect(listDocuments).toHaveBeenLastCalledWith(
      expect.objectContaining({
        folder: "folder-1",
        search: "retention",
        mime_type: "application/pdf",
        tags: ["policy"],
        modified_after: "2026-07-01",
        creator: "actor-1",
        ordering: "-updated_at",
        page: 1,
        page_size: 25,
      })
    );

    await userEvent.click(screen.getByLabelText("Select Retention policy"));
    expect(screen.getByRole("button", { name: "Download 1" })).toBeEnabled();
    await userEvent.clear(screen.getByLabelText("Search documents"));
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Download 1" })).not.toBeInTheDocument()
    );
    expect(screen.getByLabelText("Current route")).not.toHaveTextContent("search=retention");
  });

  it("routes folder and document actions and protects delete behind confirmation", async () => {
    useAuthStore.setState({ user: dmsUser, isAuthenticated: true, isLoading: false });
    vi.spyOn(dmsService, "getConfiguration").mockResolvedValue(dmsConfiguration());
    vi.spyOn(dmsService, "listFolders").mockResolvedValue({
      items: [folderFixture],
      pagination: dmsPagination,
      correlation_id: "corr-folders",
    });
    vi.spyOn(dmsService, "getFolder").mockResolvedValue(folderFixture);
    vi.spyOn(dmsService, "listDocuments").mockResolvedValue({
      items: [documentFixture],
      pagination: dmsPagination,
      correlation_id: "corr-documents",
    });
    const remove = vi.spyOn(dmsService, "deleteDocument").mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);

    renderPage();

    expect(await screen.findByRole("button", { name: "Retention policy" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Policies" }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent("folder=folder-1");

    await userEvent.click(screen.getByRole("button", { name: "Retention policy" }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent("/dms/documents/document-1");

    await userEvent.click(screen.getByRole("button", { name: "Delete Retention policy" }));
    expect(remove).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Delete Retention policy" }));
    await waitFor(() => expect(remove).toHaveBeenCalledWith("document-1"));

    await userEvent.click(screen.getByRole("button", { name: "New folder" }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent("/dms/folders/new");
  });

  it("downloads selected documents in bulk without enabling forbidden selections", async () => {
    const urls = mockDownloadUrl();
    try {
      useAuthStore.setState({ user: dmsUser, isAuthenticated: true, isLoading: false });
      vi.spyOn(dmsService, "getConfiguration").mockResolvedValue(dmsConfiguration());
      vi.spyOn(dmsService, "listFolders").mockResolvedValue({
        items: [],
        pagination: { ...dmsPagination, count: 0, total_pages: 0 },
        correlation_id: "corr-folders",
      });
      vi.spyOn(dmsService, "listDocuments").mockResolvedValue({
        items: [
          documentFixture,
          {
            ...documentFixture,
            id: "document-locked",
            name: "Locked evidence",
            allowed_actions: ["read"],
          },
        ],
        pagination: { ...dmsPagination, count: 2 },
        correlation_id: "corr-documents",
      });
      const download = vi.spyOn(dmsService, "downloadDocument").mockResolvedValue({
        blob: new Blob(["content"], { type: "application/pdf" }),
        filename: "retention-policy.pdf",
        mime_type: "application/pdf",
      });

      renderPage();

      expect(await screen.findByRole("button", { name: "Retention policy" })).toBeInTheDocument();
      await userEvent.click(screen.getByLabelText("Select Locked evidence"));
      expect(screen.getByRole("button", { name: "Download 1" })).toBeDisabled();
      await userEvent.click(screen.getByLabelText("Select Locked evidence"));
      await userEvent.click(screen.getByLabelText("Select Retention policy"));
      await userEvent.click(screen.getByRole("button", { name: "Download 1" }));
      await waitFor(() => expect(download).toHaveBeenCalledWith("document-1"));
      expect(urls.createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
      expect(urls.revokeObjectURL).toHaveBeenCalledWith("blob:dms-download");
    } finally {
      urls.restore();
    }
  });

  it("renders fail-closed when mandatory DMS configuration is unavailable", async () => {
    useAuthStore.setState({ user: dmsUser, isAuthenticated: true, isLoading: false });
    vi.spyOn(dmsService, "getConfiguration").mockRejectedValue(new Error("configuration offline"));
    vi.spyOn(dmsService, "listFolders").mockResolvedValue({
      items: [],
      pagination: { ...dmsPagination, count: 0, total_pages: 0 },
      correlation_id: "corr-folders",
    });
    vi.spyOn(dmsService, "listDocuments").mockResolvedValue({
      items: [],
      pagination: { ...dmsPagination, count: 0, total_pages: 0 },
      correlation_id: "corr-documents",
    });

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Document request failed");
    expect(screen.queryByRole("button", { name: "Upload document" })).not.toBeInTheDocument();
  });
});
