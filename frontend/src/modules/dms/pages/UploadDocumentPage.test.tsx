/* eslint-disable max-lines-per-function -- upload flow coverage keeps form fixtures local. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  dmsConfiguration,
  dmsPagination,
  documentFixture,
  folderFixture,
} from "../__tests__/fixtures";
import { dmsService } from "../services/dms-service";
import { UploadDocumentPage } from "./UploadDocumentPage";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="Current route">{`${location.pathname}${location.search}`}</output>;
}

function renderUpload(ui: ReactElement, route = "/documents/upload?folder=folder-1") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <LocationProbe />
        <Routes>
          <Route path="/documents/upload" element={ui} />
          <Route path="*" element={<span />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("UploadDocumentPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("submits a governed upload with folder, tags, metadata, and progress callback", async () => {
    vi.spyOn(dmsService, "getConfiguration").mockResolvedValue(dmsConfiguration());
    vi.spyOn(dmsService, "listFolders").mockResolvedValue({
      items: [folderFixture],
      pagination: dmsPagination,
      correlation_id: "corr-folders",
    });
    const uploadDocument = vi
      .spyOn(dmsService, "uploadDocument")
      .mockImplementation((request, options) => {
        options?.onProgress?.({ loaded: 1024, total: 2048, percent: 50 });
        return Promise.resolve({
          ...documentFixture,
          id: "document-uploaded",
          metadata: request.metadata ?? {},
        });
      });

    renderUpload(<UploadDocumentPage />);

    expect(await screen.findByRole("heading", { name: "Upload document" })).toBeInTheDocument();
    await userEvent.upload(
      screen.getByLabelText("Choose document file"),
      new File(["approved"], "retention-policy.pdf", { type: "application/pdf" })
    );
    expect(screen.getByLabelText("Document name")).toHaveValue("retention-policy");
    await userEvent.clear(screen.getByLabelText("Document name"));
    await userEvent.type(screen.getByLabelText("Document name"), "Board Retention Policy");
    await userEvent.type(screen.getByLabelText("Description"), "Approved by the board");
    fireEvent.change(screen.getByLabelText("Tags"), {
      target: { value: "Policy, Finance, Policy" },
    });
    fireEvent.change(screen.getByLabelText("Metadata key 1"), { target: { value: "owner" } });
    fireEvent.change(screen.getByLabelText("Metadata value 1"), { target: { value: "legal" } });
    await userEvent.click(screen.getByRole("button", { name: "Upload document" }));

    await waitFor(() =>
      expect(uploadDocument).toHaveBeenCalledWith(
        {
          file: expect.any(File) as File,
          name: "Board Retention Policy",
          folder_id: "folder-1",
          description: "Approved by the board",
          tags: ["policy", "finance"],
          metadata: { owner: "legal" },
        },
        expect.objectContaining({ onProgress: expect.any(Function) as () => void })
      )
    );
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/dms/documents/document-uploaded"
    );
  });

  it("blocks empty and executable files before upload and requires a document name", async () => {
    vi.spyOn(dmsService, "getConfiguration").mockResolvedValue(dmsConfiguration());
    vi.spyOn(dmsService, "listFolders").mockResolvedValue({
      items: [],
      pagination: { ...dmsPagination, count: 0, total_pages: 0 },
      correlation_id: "corr-folders",
    });
    const uploadDocument = vi.spyOn(dmsService, "uploadDocument").mockResolvedValue({
      ...documentFixture,
      metadata: {},
    });

    renderUpload(<UploadDocumentPage />, "/documents/upload");

    expect(await screen.findByText(/No folders exist yet/u)).toBeInTheDocument();
    await userEvent.upload(
      screen.getByLabelText("Choose document file"),
      new File(["blocked"], "script.exe", { type: "application/octet-stream" })
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "This extension is blocked by the tenant content policy."
    );
    expect(screen.getByRole("button", { name: "Upload document" })).toBeDisabled();

    await userEvent.upload(
      screen.getByLabelText("Choose document file"),
      new File(["approved"], "untitled.pdf", { type: "application/pdf" })
    );
    const name = screen.getByLabelText("Document name");
    fireEvent.change(name, { target: { value: "" } });
    const form = name.closest("form");
    expect(form).not.toBeNull();
    fireEvent.submit(form!);

    expect(screen.getByRole("alert")).toHaveTextContent("Document name is required.");
    expect(uploadDocument).not.toHaveBeenCalled();
  });

  it("renders fail-closed configuration errors and retries both configuration and folders", async () => {
    const getConfiguration = vi
      .spyOn(dmsService, "getConfiguration")
      .mockRejectedValueOnce(new Error("configuration offline"))
      .mockResolvedValue(dmsConfiguration());
    const listFolders = vi.spyOn(dmsService, "listFolders").mockResolvedValue({
      items: [],
      pagination: { ...dmsPagination, count: 0, total_pages: 0 },
      correlation_id: "corr-folders",
    });

    renderUpload(<UploadDocumentPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("configuration offline");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await screen.findByRole("heading", { name: "Upload document" });
    expect(getConfiguration).toHaveBeenCalledTimes(2);
    expect(listFolders).toHaveBeenCalled();
  });
});
