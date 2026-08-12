/* eslint-disable max-lines-per-function -- DMS configuration is a dense governed operator surface. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "@/stores/auth-store";
import type { DmsConfiguration, DmsConfigurationValues } from "../contracts";
import { dmsService } from "../services/dms-service";
import { DmsConfigurationPage } from "./DmsConfigurationPage";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const user = {
  id: "actor-1",
  email: "admin@example.com",
  username: "admin",
  is_staff: true,
  is_superuser: false,
  tenant_id: "tenant-1",
  platform_role: null,
  tenant_role: "tenant_admin",
};

const values: DmsConfigurationValues = {
  max_folder_depth: 5,
  max_document_tags: 8,
  max_tag_length: 40,
  max_metadata_bytes: 4096,
  max_share_lifetime_days: 30,
  max_share_access_count: 10,
  permission_implications: {
    read: [],
    write: ["read"],
    delete: ["manage"],
    share: ["read"],
    manage: ["write"],
  },
  principal_search_min_limit: 1,
  principal_search_max_limit: 50,
  principal_search_default_limit: 10,
  principal_query_min_length: 2,
  principal_query_max_length: 80,
  max_name_length: 120,
  forbidden_name_characters: ["/", "\0"],
  max_metadata_key_length: 64,
  folder_deletion_policy: "empty_only",
  download_verification_chunk_size: 1024,
  storage_backend: "local",
  max_document_search_length: 120,
  document_ordering_fields: ["name", "-updated_at"],
  default_document_ordering: "-updated_at",
  restore_note_template: "Restore approved version",
  share_token_entropy_bytes: 32,
  share_token_prefix_length: 8,
  incoming_share_token_max_length: 128,
  metadata_namespace_max_length: 32,
  max_upload_bytes: 1048576,
  storage_stream_chunk_size: 8192,
  content_inspection_window_bytes: 2048,
  storage_key_max_length: 256,
  blocked_file_signatures: ["4d5a"],
  permitted_mime_types: ["application/pdf", "text/plain"],
  max_control_character_ratio_percent: 20,
  min_control_characters: 3,
  storage_backend_name_max_length: 40,
  outbox_freshness_seconds: 60,
  collection_search_max_length: 120,
  tag_filter_max_tags: 5,
  tag_filter_max_length: 40,
  version_change_note_max_length: 160,
  api_read_quota: 1000,
  api_write_quota: 500,
  storage_quota_bytes: 1073741824,
  folder_page_size: 25,
  document_page_size: 25,
  max_page_size: 100,
  default_share_expiry_hours: 24,
  default_share_access_count: 2,
  text_preview_max_characters: 2000,
  upload_timeout_ms: 30000,
  upload_max_retries: 2,
  circuit_breaker_failure_threshold: 3,
  circuit_breaker_reset_ms: 60000,
  executable_extensions: [".exe"],
  governance_required_operations: ["delete", "share"],
  feature_flags: { governed_sharing: true },
  rollout: { enabled: true, roles: ["tenant_admin"], cohorts: ["default"] },
};

function currentConfiguration(overrides: Partial<DmsConfigurationValues> = {}): DmsConfiguration {
  return {
    id: "config-1",
    tenant_id: "tenant-1",
    environment: "default" as const,
    version: 3,
    values: { ...values, ...overrides },
    updated_by: "actor-1",
    created_at: "2026-07-20T00:00:00Z",
    updated_at: "2026-07-22T00:00:00Z",
  };
}

function page(items: readonly unknown[]) {
  return {
    items,
    pagination: {
      count: items.length,
      page: 1,
      page_size: 25,
      total_pages: items.length ? 1 : 0,
      has_next: false,
      has_previous: false,
    },
    correlation_id: "corr-dms",
  };
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DmsConfigurationPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("DmsConfigurationPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useAuthStore.setState({ user, isAuthenticated: true, isLoading: false });
    vi.spyOn(dmsService, "getConfiguration").mockResolvedValue(currentConfiguration());
    vi.spyOn(dmsService, "configurationHistory").mockResolvedValue(
      page([
        {
          id: "history-1",
          version: 2,
          environment: "default",
          values,
          created_by: "actor-2",
          correlation_id: "corr-history",
          created_at: "2026-07-21T00:00:00Z",
        },
      ]) as never
    );
    vi.spyOn(dmsService, "configurationAudit").mockResolvedValue(
      page([
        {
          id: "audit-1",
          actor_id: "actor-2",
          action: "updated",
          correlation_id: "corr-audit",
          from_version: 1,
          to_version: 2,
          before: {},
          after: values,
          created_at: "2026-07-21T00:00:00Z",
        },
      ]) as never
    );
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false });
  });

  it("requires a server preview before saving and renders history/audit evidence", async () => {
    const preview = vi.spyOn(dmsService, "previewConfiguration").mockResolvedValue({
      valid: true,
      normalized_values: { ...values, max_folder_depth: 7 },
      changes: [{ field: "max_folder_depth", before: 5, after: 7 }],
      restart_required: false,
    });
    const save = vi
      .spyOn(dmsService, "updateConfiguration")
      .mockResolvedValue(currentConfiguration());

    renderPage();
    expect(await screen.findByRole("heading", { name: "DMS configuration" })).toBeInTheDocument();
    expect(screen.getByText(/Correlation corr-history/u)).toBeInTheDocument();
    expect(screen.getByText(/Correlation corr-audit/u)).toBeInTheDocument();

    const saveButton = screen.getByRole("button", { name: "Save version" });
    expect(saveButton).toBeDisabled();
    await userEvent.clear(screen.getByLabelText("Maximum folder depth"));
    await userEvent.type(screen.getByLabelText("Maximum folder depth"), "7");
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));
    expect(await screen.findByText("max_folder_depth")).toBeInTheDocument();
    const previewRequest = preview.mock.calls.at(-1)?.[0];
    expect(previewRequest?.environment).toBe("default");
    expect(previewRequest?.values.max_folder_depth).toBe(7);
    await userEvent.click(screen.getByRole("button", { name: "Save version" }));
    await waitFor(() =>
      expect(save).toHaveBeenCalledWith(expect.objectContaining({ environment: "default" }))
    );
  }, 10_000);

  it("blocks invalid drafts and keeps read-only users from mutating configuration", async () => {
    useAuthStore.setState({
      user: { ...user, is_staff: false, tenant_role: "viewer" },
      isAuthenticated: true,
      isLoading: false,
    });
    renderPage();

    expect(await screen.findByText(/read-only configuration access/u)).toBeInTheDocument();
    expect(screen.getByLabelText("Maximum folder depth")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Preview" })).not.toBeInTheDocument();
  });

  it("exports and rolls back only after explicit operator confirmation", async () => {
    const createObjectURL = vi.fn(() => "blob:dms-config");
    const revokeObjectURL = vi.fn();
    const click = vi.fn();
    const originalCreateElement = document.createElement.bind(document);
    const anchor = document.createElement("a");
    anchor.click = click;
    vi.spyOn(document, "createElement").mockImplementation((tag) =>
      tag === "a" ? anchor : originalCreateElement(tag)
    );
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL });
    vi.spyOn(dmsService, "exportConfiguration").mockResolvedValue({
      schema_version: 1,
      module: "dms",
      environment: "default",
      version: 3,
      values,
    });
    const rollback = vi
      .spyOn(dmsService, "rollbackConfiguration")
      .mockResolvedValue(currentConfiguration());
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Export" }));
    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
    expect(anchor.download).toBe("dms-default-v3.json");
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:dms-config");

    await userEvent.click(screen.getByRole("button", { name: "Rollback" }));
    await waitFor(() => expect(rollback).toHaveBeenCalledWith(2, "default"));
  });

  it("imports only valid DMS configuration export documents", async () => {
    const importConfiguration = vi
      .spyOn(dmsService, "importConfiguration")
      .mockResolvedValue(currentConfiguration({ max_folder_depth: 9 }));
    const toast = await import("sonner");
    const rendered = renderPage();

    await screen.findByRole("heading", { name: "DMS configuration" });
    const input = rendered.container.querySelector(
      'input[aria-label="Import DMS configuration JSON"]'
    );
    if (!(input instanceof HTMLInputElement)) throw new Error("DMS import input was not rendered.");

    await userEvent.upload(
      input,
      new File([JSON.stringify({ module: "email_marketing" })], "wrong-module.json", {
        type: "application/json",
      })
    );
    await waitFor(() =>
      expect(toast.toast.error).toHaveBeenCalledWith(
        "The file is not a DMS configuration export document."
      )
    );
    expect(importConfiguration).not.toHaveBeenCalled();

    const document = {
      schema_version: 1,
      module: "dms",
      environment: "staging",
      version: 3,
      values: { ...values, max_folder_depth: 9 },
    };
    await userEvent.upload(
      input,
      new File([JSON.stringify(document)], "dms-config.json", { type: "application/json" })
    );

    await waitFor(() => expect(importConfiguration).toHaveBeenCalledWith(document));
  });

  it("fails closed on invalid import JSON without calling the import endpoint", async () => {
    const importConfiguration = vi.spyOn(dmsService, "importConfiguration");
    const toast = await import("sonner");
    const rendered = renderPage();

    await screen.findByRole("heading", { name: "DMS configuration" });
    const input = rendered.container.querySelector(
      'input[aria-label="Import DMS configuration JSON"]'
    );
    if (!(input instanceof HTMLInputElement)) throw new Error("DMS import input was not rendered.");

    await userEvent.upload(input, new File(["{"], "broken.json", { type: "application/json" }));

    await waitFor(() =>
      expect(toast.toast.error).toHaveBeenCalledWith("The configuration file is not valid JSON.")
    );
    expect(importConfiguration).not.toHaveBeenCalled();
  });

  it("renders fail-closed query and empty-response states without mutation controls", async () => {
    vi.spyOn(dmsService, "getConfiguration").mockRejectedValue(new Error("DMS config unavailable"));
    const failed = renderPage();

    expect(await screen.findByText("DMS config unavailable")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Preview" })).not.toBeInTheDocument();
    failed.unmount();

    vi.spyOn(dmsService, "getConfiguration").mockResolvedValue(null as never);
    renderPage();

    expect(
      await screen.findByText("The governed DMS configuration response was empty.")
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save version" })).not.toBeInTheDocument();
  });

  it("shows empty history/audit and blocks invalid drafts before preview", async () => {
    vi.spyOn(dmsService, "configurationHistory").mockResolvedValue(page([]) as never);
    vi.spyOn(dmsService, "configurationAudit").mockResolvedValue(page([]) as never);
    const preview = vi.spyOn(dmsService, "previewConfiguration");

    renderPage();

    expect(await screen.findByText("No prior configuration versions.")).toBeInTheDocument();
    expect(screen.getByText("No audit records were returned.")).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Permitted MIME types"));

    expect(
      await screen.findByText("The MIME-type allow-list is fail-closed and cannot be empty.")
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save version" })).toBeDisabled();
    expect(preview).not.toHaveBeenCalled();
  });

  it("surfaces preview mutation failures and keeps save disabled", async () => {
    vi.spyOn(dmsService, "previewConfiguration").mockRejectedValue(
      new Error("Server rejected DMS policy")
    );
    const save = vi.spyOn(dmsService, "updateConfiguration");

    renderPage();

    await userEvent.clear(await screen.findByLabelText("Maximum folder depth"));
    await userEvent.type(screen.getByLabelText("Maximum folder depth"), "6");
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));

    expect(await screen.findByText("Server rejected DMS policy")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save version" })).toBeDisabled();
    expect(save).not.toHaveBeenCalled();
  });
});
