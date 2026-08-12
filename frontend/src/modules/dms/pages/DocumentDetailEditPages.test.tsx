/* eslint-disable max-lines-per-function -- focused page workflow coverage keeps fixtures local. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  dmsConfiguration,
  dmsPagination,
  documentFixture,
  folderFixture,
} from "../__tests__/fixtures";
import { dmsService } from "../services/dms-service";
import { DocumentDetailPage } from "./DocumentDetailPage";
import { CreateFolderPage } from "./CreateFolderPage";
import { EditDocumentPage } from "./EditDocumentPage";
import { EditFolderPage } from "./EditFolderPage";
import { FolderDetailPage } from "./FolderDetailPage";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="Current route">{`${location.pathname}${location.search}`}</output>;
}

function renderRoute(path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <LocationProbe />
        <Routes>
          <Route path="/dms/documents/:id" element={<DocumentDetailPage />} />
          <Route path="/dms/documents/:id/edit" element={<EditDocumentPage />} />
          <Route path="/dms/folders/new" element={<CreateFolderPage />} />
          <Route path="/dms/folders/:id" element={<FolderDetailPage />} />
          <Route path="/dms/folders/:id/edit" element={<EditFolderPage />} />
          <Route path="*" element={<span>navigated</span>} />
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
  anchor.click = vi.fn();
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: vi.fn(() => "blob:dms-detail-download"),
  });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  vi.spyOn(document, "createElement").mockImplementation((tagName) =>
    tagName === "a" ? anchor : originalCreateElement(tagName)
  );
  return () => {
    if (originalCreateObjectURL)
      Object.defineProperty(URL, "createObjectURL", originalCreateObjectURL);
    else Reflect.deleteProperty(URL, "createObjectURL");
    if (originalRevokeObjectURL)
      Object.defineProperty(URL, "revokeObjectURL", originalRevokeObjectURL);
    else Reflect.deleteProperty(URL, "revokeObjectURL");
  };
}

describe("DMS document detail and edit pages", () => {
  afterEach(() => vi.restoreAllMocks());

  it("runs document detail download, tab navigation, guarded delete, and metadata navigation", async () => {
    const restoreUrl = mockDownloadUrl();
    try {
      vi.spyOn(dmsService, "getDocument").mockResolvedValue({
        ...documentFixture,
        metadata: { owner: "legal", retention: "7y" },
        allowed_actions: ["read", "download", "write", "delete", "manage", "share"],
      });
      vi.spyOn(dmsService, "listVersions").mockResolvedValue({
        items: [],
        pagination: { ...dmsPagination, count: 0, total_pages: 0 },
        correlation_id: "corr-versions",
      });
      const download = vi.spyOn(dmsService, "downloadDocument").mockResolvedValue({
        blob: new Blob(["content"], { type: "application/pdf" }),
        filename: "retention-policy.pdf",
        mime_type: "application/pdf",
      });
      const remove = vi.spyOn(dmsService, "deleteDocument").mockResolvedValue(undefined);
      vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);

      const firstRender = renderRoute("/dms/documents/document-1");

      expect(await screen.findByRole("heading", { name: "Retention policy" })).toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: "Download" }));
      await waitFor(() => expect(download).toHaveBeenCalledWith("document-1"));
      await userEvent.click(screen.getByRole("button", { name: "New version" }));
      expect(screen.getByRole("tab", { name: "Versions" })).toHaveAttribute(
        "aria-selected",
        "true"
      );
      await userEvent.click(screen.getByRole("button", { name: "Edit metadata" }));
      expect(screen.getByLabelText("Current route")).toHaveTextContent(
        "/dms/documents/document-1/edit"
      );
      firstRender.unmount();

      renderRoute("/dms/documents/document-1");
      await screen.findByRole("heading", { name: "Retention policy" });
      await userEvent.click(screen.getByRole("button", { name: "Delete" }));
      expect(remove).not.toHaveBeenCalled();
      await userEvent.click(screen.getByRole("button", { name: "Delete" }));
      await waitFor(() => expect(remove).toHaveBeenCalledWith("document-1"));
      expect(screen.getByLabelText("Current route")).toHaveTextContent("/dms/documents");
    } finally {
      restoreUrl();
    }
  });

  it("saves document metadata with optimistic revision and moves only when folder changed", async () => {
    vi.spyOn(dmsService, "getConfiguration").mockResolvedValue(dmsConfiguration());
    vi.spyOn(dmsService, "getDocument").mockResolvedValue({
      ...documentFixture,
      metadata: { owner: "legal" },
      allowed_actions: ["read", "write"],
    });
    vi.spyOn(dmsService, "listFolders").mockResolvedValue({
      items: [
        folderFixture,
        { ...folderFixture, id: "folder-2", name: "Archive", path: "/Archive" },
      ],
      pagination: { ...dmsPagination, count: 2 },
      correlation_id: "corr-folders",
    });
    const update = vi.spyOn(dmsService, "updateDocument").mockResolvedValue({
      ...documentFixture,
      name: "Retention policy 2026",
      metadata: { owner: "compliance" },
      updated_at: "2026-07-23T00:00:00Z",
    });
    const move = vi.spyOn(dmsService, "moveDocument").mockResolvedValue({
      ...documentFixture,
      name: "Retention policy 2026",
      folder_id: "folder-2",
      metadata: { owner: "compliance" },
      updated_at: "2026-07-24T00:00:00Z",
    });

    renderRoute("/dms/documents/document-1/edit");

    const name = await screen.findByLabelText("Document name");
    await userEvent.clear(name);
    await userEvent.type(name, "Retention policy 2026");
    await userEvent.selectOptions(screen.getByLabelText("Folder"), "folder-2");
    await userEvent.clear(screen.getByLabelText("Metadata value 1"));
    await userEvent.type(screen.getByLabelText("Metadata value 1"), "compliance");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(update).toHaveBeenCalledWith("document-1", {
        name: "Retention policy 2026",
        description: "Board-approved retention policy",
        tags: ["policy", "retention"],
        metadata: { owner: "compliance" },
        expected_updated_at: "2026-07-22T00:00:00Z",
      })
    );
    expect(move).toHaveBeenCalledWith("document-1", {
      folder_id: "folder-2",
      expected_updated_at: "2026-07-23T00:00:00Z",
    });
    expect(screen.getByLabelText("Current route")).toHaveTextContent("/dms/documents/document-1");
  });

  it("blocks folder moves that exceed governed depth and submits valid rename/move payloads", async () => {
    vi.spyOn(dmsService, "getConfiguration").mockResolvedValue(
      dmsConfiguration({ max_folder_depth: 2 })
    );
    vi.spyOn(dmsService, "getFolder").mockResolvedValue(folderFixture);
    vi.spyOn(dmsService, "listFolders").mockResolvedValue({
      items: [
        folderFixture,
        {
          ...folderFixture,
          id: "folder-child",
          name: "Policies child",
          path: "/Policies/Policies child",
          depth: 1,
          parent_id: "folder-1",
        },
        { ...folderFixture, id: "folder-2", name: "Archive", path: "/Archive", depth: 0 },
        {
          ...folderFixture,
          id: "folder-3",
          name: "Nested",
          path: "/Archive/Nested",
          depth: 1,
          parent_id: "folder-2",
        },
      ],
      pagination: { ...dmsPagination, count: 3 },
      correlation_id: "corr-folders",
    });
    const update = vi.spyOn(dmsService, "updateFolder").mockResolvedValue({
      ...folderFixture,
      name: "Policies 2026",
    });
    const move = vi.spyOn(dmsService, "moveFolder").mockResolvedValue({
      ...folderFixture,
      name: "Policies 2026",
      parent_id: "folder-2",
    });

    renderRoute("/dms/folders/folder-1/edit");

    const name = await screen.findByLabelText("Folder name");
    await userEvent.clear(name);
    await userEvent.type(name, "Policies 2026");
    await userEvent.selectOptions(screen.getByLabelText("Parent folder"), "folder-3");
    expect(screen.getByRole("button", { name: "Save folder" })).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent("maximum depth of 2");

    await userEvent.selectOptions(screen.getByLabelText("Parent folder"), "folder-2");
    await userEvent.click(screen.getByRole("button", { name: "Save folder" }));
    await waitFor(() =>
      expect(update).toHaveBeenCalledWith("folder-1", {
        name: "Policies 2026",
        description: "Governed tenant documents",
        sort_order: 1,
      })
    );
    expect(move).toHaveBeenCalledWith("folder-1", { parent_id: "folder-2" });
    expect(screen.getByLabelText("Current route")).toHaveTextContent("/dms/folders/folder-1");
  });

  it("renders folder contents, blocks non-empty deletion, and deletes only after confirmation", async () => {
    const deleteFolder = vi.spyOn(dmsService, "deleteFolder").mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    vi.spyOn(dmsService, "getFolderContents")
      .mockResolvedValueOnce({
        folder: { ...folderFixture, allowed_actions: ["read", "create", "write", "delete"] },
        breadcrumbs: [folderFixture],
        folders: [{ ...folderFixture, id: "folder-child", name: "Archive", depth: 1 }],
        folders_pagination: dmsPagination,
        documents: [documentFixture],
        documents_pagination: dmsPagination,
        allowed_actions: ["read", "create", "write", "delete"],
      })
      .mockResolvedValue({
        folder: { ...folderFixture, allowed_actions: ["read", "create", "write", "delete"] },
        breadcrumbs: [folderFixture],
        folders: [],
        folders_pagination: { ...dmsPagination, count: 0 },
        documents: [],
        documents_pagination: { ...dmsPagination, count: 0 },
        allowed_actions: ["read", "create", "write", "delete"],
      });

    const firstRender = renderRoute("/dms/folders/folder-1");

    expect(await screen.findByRole("heading", { name: "Policies" })).toBeInTheDocument();
    expect(screen.getByText(/Deletion is guarded/u)).toHaveTextContent(
      "1 child folder and 1 document"
    );
    expect(screen.getByRole("button", { name: "Delete" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: /^Archive/u }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent("/dms/folders/folder-child");
    firstRender.unmount();

    renderRoute("/dms/folders/folder-1");
    expect(await screen.findByText("Upload first document")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(deleteFolder).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(deleteFolder).toHaveBeenCalledWith("folder-1"));
    expect(screen.getByLabelText("Current route")).toHaveTextContent("/dms/documents");
  });

  it("creates root folders from governed defaults and blocks duplicate sibling names", async () => {
    vi.spyOn(dmsService, "getConfiguration").mockResolvedValue(dmsConfiguration());
    vi.spyOn(dmsService, "listFolders").mockResolvedValue({
      items: [folderFixture],
      pagination: { ...dmsPagination, count: 1 },
      correlation_id: "corr-folders",
    });
    const create = vi.spyOn(dmsService, "createFolder").mockResolvedValue({
      ...folderFixture,
      id: "folder-2026",
      name: "Policies 2026",
      path: "/Policies 2026",
    });

    renderRoute("/dms/folders/new");

    const name = await screen.findByLabelText("Folder name");
    await userEvent.type(name, "Policies");
    expect(screen.getByRole("button", { name: "Create folder" })).toBeDisabled();
    expect(screen.getByText("A sibling folder already uses this name.")).toBeInTheDocument();

    await userEvent.clear(name);
    await userEvent.type(name, "Policies 2026");
    await userEvent.type(screen.getByLabelText("Description"), "Board policies for FY2026");
    await userEvent.click(screen.getByRole("button", { name: "Create folder" }));

    await waitFor(() =>
      expect(create).toHaveBeenCalledWith({
        name: "Policies 2026",
        description: "Board policies for FY2026",
        parent_id: null,
      })
    );
    expect(screen.getByLabelText("Current route")).toHaveTextContent("/dms/folders/folder-2026");
  });

  it("keeps folder creation fail-closed when governed configuration is unavailable", async () => {
    vi.spyOn(dmsService, "getConfiguration").mockRejectedValue(new Error("config offline"));
    vi.spyOn(dmsService, "listFolders").mockResolvedValue({
      items: [],
      pagination: { ...dmsPagination, count: 0 },
      correlation_id: "corr-folders",
    });
    const create = vi.spyOn(dmsService, "createFolder");

    renderRoute("/dms/folders/new");

    expect(await screen.findByRole("alert")).toHaveTextContent("config offline");
    expect(create).not.toHaveBeenCalled();
  });
});
