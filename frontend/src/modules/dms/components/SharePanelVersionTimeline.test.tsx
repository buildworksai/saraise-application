/* eslint-disable max-lines-per-function -- focused DMS behavior coverage uses local service fixtures. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { dmsConfiguration, dmsPagination } from "../__tests__/fixtures";
import type { DocumentShare, DocumentVersion } from "../contracts";
import { dmsService } from "../services/dms-service";
import { SharePanel } from "./SharePanel";
import { VersionTimeline } from "./VersionTimeline";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

function renderWithQuery(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const activeShare: DocumentShare = {
  id: "share-1",
  document_id: "document-1",
  version_id: "version-2",
  token_prefix: "tok_1234",
  expires_at: "2026-07-23T00:00:00Z",
  max_access_count: 2,
  access_count: 1,
  last_accessed_at: null,
  revoked_at: null,
  created_by: "actor-1",
  created_at: "2026-07-22T00:00:00Z",
  state: "active",
};

const versionCurrent: DocumentVersion = {
  id: "version-2",
  document_id: "document-1",
  version_number: 2,
  original_filename: "policy-v2.pdf",
  mime_type: "application/pdf",
  size_bytes: 2048,
  checksum_sha256: "sha256-fixture-current",
  change_note: "Board approved",
  source_version_id: null,
  created_by: "actor-1",
  created_at: "2026-07-22T00:00:00Z",
};

const versionPrevious: DocumentVersion = {
  ...versionCurrent,
  id: "version-1",
  version_number: 1,
  original_filename: "policy-v1.pdf",
  size_bytes: 1024,
  checksum_sha256: "sha256-fixture-previous",
  change_note: "",
  created_at: "2026-07-20T00:00:00Z",
};

describe("SharePanel and VersionTimeline", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("creates a governed one-time share, exposes copy once, and allows dismissal", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    vi.spyOn(dmsService, "getConfiguration").mockResolvedValue(dmsConfiguration());
    vi.spyOn(dmsService, "listShares").mockResolvedValue({
      items: [],
      pagination: { ...dmsPagination, count: 0, total_pages: 0 },
      correlation_id: "corr-shares",
    });
    const createShare = vi.spyOn(dmsService, "createShare").mockResolvedValue({
      share: activeShare,
      share_url: "https://share.example/token",
    });

    renderWithQuery(<SharePanel documentId="document-1" canShare />);

    await userEvent.click(await screen.findByRole("button", { name: "Create first share" }));
    await userEvent.click(screen.getByRole("button", { name: "Create share" }));

    await waitFor(() =>
      expect(createShare).toHaveBeenCalledWith({
        document_id: "document-1",
        expires_at: expect.any(String) as string,
        max_access_count: 2,
      })
    );
    expect(await screen.findByLabelText("One-time share URL")).toHaveValue(
      "https://share.example/token"
    );

    await userEvent.click(screen.getByRole("button", { name: "Copy" }));
    expect(writeText).toHaveBeenCalledWith("https://share.example/token");
    expect(screen.getByRole("button", { name: "Copied" })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "I have saved it" }));
    expect(screen.queryByLabelText("One-time share URL")).not.toBeInTheDocument();
  });

  it("renders existing shares read-only without share permission and revokes active shares with permission", async () => {
    vi.spyOn(dmsService, "getConfiguration").mockResolvedValue(dmsConfiguration());
    vi.spyOn(dmsService, "listShares").mockResolvedValue({
      items: [activeShare],
      pagination: dmsPagination,
      correlation_id: "corr-shares",
    });
    const revokeShare = vi.spyOn(dmsService, "revokeShare").mockResolvedValue(activeShare);

    const first = renderWithQuery(<SharePanel documentId="document-1" canShare={false} />);
    expect(await screen.findByText("Token prefix tok_1234")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create share" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Revoke" })).not.toBeInTheDocument();
    first.unmount();

    renderWithQuery(<SharePanel documentId="document-1" canShare />);
    await userEvent.click(await screen.findByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(revokeShare).toHaveBeenCalledWith("share-1"));
  });

  it("restores only non-current versions after confirmation and downloads immutable content", async () => {
    const originalCreateObjectURL = Object.getOwnPropertyDescriptor(URL, "createObjectURL");
    const originalRevokeObjectURL = Object.getOwnPropertyDescriptor(URL, "revokeObjectURL");
    const originalCreateElement = document.createElement.bind(document);
    const anchor = originalCreateElement("a");
    anchor.click = vi.fn();
    vi.spyOn(document, "createElement").mockImplementation((tagName) =>
      tagName === "a" ? anchor : originalCreateElement(tagName)
    );
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:dms"),
    });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    vi.spyOn(dmsService, "getConfiguration").mockResolvedValue(dmsConfiguration());
    vi.spyOn(dmsService, "listVersions").mockResolvedValue({
      items: [versionCurrent, versionPrevious],
      pagination: dmsPagination,
      correlation_id: "corr-versions",
    });
    const restoreVersion = vi.spyOn(dmsService, "restoreVersion").mockResolvedValue({
      ...versionCurrent,
      id: "version-3",
      version_number: 3,
      source_version_id: "version-1",
    });
    const downloadDocument = vi.spyOn(dmsService, "downloadDocument").mockResolvedValue({
      blob: new Blob(["pdf"], { type: "application/pdf" }),
      filename: "policy-v2.pdf",
      mime_type: "application/pdf",
    });
    vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);

    try {
      renderWithQuery(
        <VersionTimeline documentId="document-1" canCreate={false} canRestore canDownload />
      );

      expect(await screen.findByText("Version 2")).toBeInTheDocument();
      expect(screen.getAllByRole("button", { name: "Download" })).toHaveLength(2);
      expect(screen.getAllByRole("button", { name: "Restore" })).toHaveLength(1);
      await userEvent.click(screen.getAllByRole("button", { name: "Download" })[0]!);
      expect(downloadDocument).toHaveBeenCalledWith("document-1", "version-2");
      await userEvent.click(screen.getByRole("button", { name: "Restore" }));
      expect(restoreVersion).not.toHaveBeenCalled();
      await userEvent.click(screen.getByRole("button", { name: "Restore" }));
      await waitFor(() =>
        expect(restoreVersion).toHaveBeenCalledWith("version-1", {
          change_note: "Restore approved version",
        })
      );
    } finally {
      if (originalCreateObjectURL)
        Object.defineProperty(URL, "createObjectURL", originalCreateObjectURL);
      else Reflect.deleteProperty(URL, "createObjectURL");
      if (originalRevokeObjectURL)
        Object.defineProperty(URL, "revokeObjectURL", originalRevokeObjectURL);
      else Reflect.deleteProperty(URL, "revokeObjectURL");
    }
  });

  it("blocks unsafe replacement files and uploads valid versions with progress evidence", async () => {
    vi.spyOn(dmsService, "getConfiguration").mockResolvedValue(dmsConfiguration());
    vi.spyOn(dmsService, "listVersions").mockResolvedValue({
      items: [versionCurrent],
      pagination: dmsPagination,
      correlation_id: "corr-versions",
    });
    const createVersion = vi
      .spyOn(dmsService, "createVersion")
      .mockImplementation((_request, options) => {
        options?.onProgress?.({ loaded: 512, total: 1024, percent: 50 });
        return Promise.resolve({ ...versionCurrent, id: "version-3", version_number: 3 });
      });

    renderWithQuery(
      <VersionTimeline documentId="document-1" canCreate canRestore={false} canDownload={false} />
    );

    await userEvent.click(await screen.findByRole("button", { name: "Upload new version" }));
    await userEvent.upload(
      screen.getByLabelText("Replacement file"),
      new File(["blocked"], "malware.exe", { type: "application/octet-stream" })
    );
    expect(screen.getByRole("alert")).toHaveTextContent("blocked by the configured extension");
    expect(screen.getByRole("button", { name: "Upload version" })).toBeDisabled();

    await userEvent.upload(
      screen.getByLabelText("Replacement file"),
      new File(["approved"], "policy-v3.pdf", { type: "application/pdf" })
    );
    await userEvent.type(screen.getByLabelText("Change note"), "Updated retention schedule");
    await userEvent.click(screen.getByRole("button", { name: "Upload version" }));

    await waitFor(() =>
      expect(createVersion).toHaveBeenCalledWith(
        {
          document_id: "document-1",
          file: expect.any(File) as File,
          change_note: "Updated retention schedule",
        },
        expect.objectContaining({ onProgress: expect.any(Function) as () => void })
      )
    );
  });
});
