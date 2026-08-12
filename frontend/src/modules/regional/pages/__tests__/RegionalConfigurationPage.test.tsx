/* eslint-disable max-lines-per-function -- coverage exercises the complete configuration workflow. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { RegionalConfigurationPage } from "../RegionalConfigurationPage";
import { regionalService } from "../../services/regional-service";
import { configurationFixture } from "./regional-test-fixtures";

const auth = vi.hoisted(() => ({ tenantRole: "tenant_admin" as string | null }));

vi.mock("../../services/regional-service");
vi.mock("@/stores/auth-store", () => ({
  useAuthStore: (selector: (state: { user: { tenant_role: string | null } }) => unknown) =>
    selector({ user: { tenant_role: auth.tenantRole } }),
}));

function renderPage() {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
        })
      }
    >
      <RegionalConfigurationPage />
    </QueryClientProvider>
  );
}

describe("RegionalConfigurationPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    auth.tenantRole = "tenant_admin";
    vi.mocked(regionalService.getConfiguration).mockResolvedValue(configurationFixture());
    vi.mocked(regionalService.listConfigurationHistory).mockResolvedValue([]);
  });

  it("loads every configuration section from the RBAC-gated API", async () => {
    renderPage();
    expect(await screen.findByText("Resource defaults and safe limits")).toBeInTheDocument();
    expect(screen.getByText("Workflow and API policy")).toBeInTheDocument();
    expect(screen.getByText("Version history and immutable audit")).toBeInTheDocument();
    expect(regionalService.getConfiguration).toHaveBeenCalledWith("development");
  });

  it("fails closed for a non-administrator without requesting tenant configuration", () => {
    auth.tenantRole = "tenant_user";
    renderPage();
    expect(screen.getByText("Access denied")).toBeInTheDocument();
    expect(regionalService.getConfiguration).not.toHaveBeenCalled();
  });

  it("validates staged JSON before previewing and applies a server dry-run result", async () => {
    const user = userEvent.setup();
    const staged = configurationFixture().document;
    vi.mocked(regionalService.previewConfiguration).mockResolvedValue({
      valid: true,
      document: staged,
      changes: [{ path: "api.default_page_size", before: 25, after: 50 }],
    });
    vi.mocked(regionalService.updateConfiguration).mockResolvedValue({
      ...configurationFixture(),
      version: 2,
      document: staged,
    });

    renderPage();
    await user.clear(await screen.findByLabelText("Complete configuration document"));
    fireEvent.change(screen.getByLabelText("Complete configuration document"), {
      target: { value: "{" },
    });
    await user.click(screen.getByRole("button", { name: "Validate and stage JSON" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/JSON/u);
    expect(regionalService.previewConfiguration).not.toHaveBeenCalled();
    expect(regionalService.updateConfiguration).not.toHaveBeenCalled();

    const changed = {
      ...staged,
      api: { ...staged.api, default_page_size: 50 },
    };
    await user.clear(screen.getByLabelText("Complete configuration document"));
    fireEvent.change(screen.getByLabelText("Complete configuration document"), {
      target: { value: JSON.stringify(changed, null, 2) },
    });
    await user.click(screen.getByRole("button", { name: "Validate and stage JSON" }));
    await user.click(screen.getByRole("button", { name: "Preview" }));

    await waitFor(() =>
      expect(regionalService.previewConfiguration).toHaveBeenCalledWith("development", changed)
    );
    expect(await screen.findByText("Dry-run diff")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Apply version" }));
    await waitFor(() =>
      expect(regionalService.updateConfiguration).toHaveBeenCalledWith({
        environment: "development",
        document: changed,
      })
    );
  });

  it("blocks preview and apply when configuration-as-code violates server allow-list policy", async () => {
    const user = userEvent.setup();
    const invalid = {
      ...configurationFixture().document,
      resource: {
        ...configurationFixture().document.resource,
        allowed_config_keys: ["country_code"],
        default_config: { jurisdiction_type: "state" },
      },
    };

    renderPage();
    await user.clear(await screen.findByLabelText("Complete configuration document"));
    fireEvent.change(screen.getByLabelText("Complete configuration document"), {
      target: { value: JSON.stringify(invalid, null, 2) },
    });
    await user.click(screen.getByRole("button", { name: "Validate and stage JSON" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Default resource configuration uses a disabled key."
    );
    expect(regionalService.previewConfiguration).not.toHaveBeenCalled();
    expect(regionalService.updateConfiguration).not.toHaveBeenCalled();
  });

  it("reloads the selected environment and applies the staged environment-specific document", async () => {
    const user = userEvent.setup();
    const selfHosted = {
      ...configurationFixture(),
      environment: "self-hosted" as const,
      document: {
        ...configurationFixture().document,
        resource: {
          ...configurationFixture().document.resource,
          name_default: "Self-hosted region",
        },
      },
    };
    vi.mocked(regionalService.getConfiguration).mockImplementation((environment) =>
      Promise.resolve(environment === "self-hosted" ? selfHosted : configurationFixture())
    );
    vi.mocked(regionalService.previewConfiguration).mockResolvedValue({
      valid: true,
      document: selfHosted.document,
      changes: [
        { path: "resource.name_default", before: "Regional resource", after: "Self-hosted region" },
      ],
    });
    vi.mocked(regionalService.updateConfiguration).mockResolvedValue({
      ...selfHosted,
      version: 2,
    });

    renderPage();
    await user.selectOptions(await screen.findByLabelText("Environment"), "self-hosted");

    await waitFor(() =>
      expect(regionalService.getConfiguration).toHaveBeenCalledWith("self-hosted")
    );
    expect(await screen.findByDisplayValue("Self-hosted region")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Preview" }));
    await waitFor(() =>
      expect(regionalService.previewConfiguration).toHaveBeenCalledWith(
        "self-hosted",
        selfHosted.document
      )
    );
    await user.click(screen.getByRole("button", { name: "Apply version" }));
    await waitFor(() =>
      expect(regionalService.updateConfiguration).toHaveBeenCalledWith({
        environment: "self-hosted",
        document: selfHosted.document,
      })
    );
  });

  it("fails closed and keeps mutation endpoints idle when configuration loading fails", async () => {
    vi.mocked(regionalService.getConfiguration).mockRejectedValue(
      new Error("regional policy down")
    );

    renderPage();

    expect(await screen.findByText("Configuration unavailable")).toBeInTheDocument();
    expect(screen.getByText("regional policy down")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Preview" })).not.toBeInTheDocument();
    expect(regionalService.previewConfiguration).not.toHaveBeenCalled();
    expect(regionalService.updateConfiguration).not.toHaveBeenCalled();
  });

  it("exports, imports, and rolls back tenant configuration with audit evidence", async () => {
    const user = userEvent.setup();
    const exported = {
      schema_version: "1.0" as const,
      environment: "development" as const,
      version: 7,
      document: configurationFixture().document,
      exported_at: "2026-07-23T11:00:00Z",
    };
    vi.mocked(regionalService.listConfigurationHistory).mockResolvedValue([
      {
        id: "history-1",
        environment: "development",
        version: 1,
        document: exported.document,
        operation: "update",
        actor_id: "operator-1",
        correlation_id: "corr-history-1",
        previous_version: null,
        created_at: "2026-07-23T10:00:00Z",
      },
      {
        id: "history-2",
        environment: "development",
        version: 2,
        document: exported.document,
        operation: "update",
        actor_id: "operator-2",
        correlation_id: "corr-history-2",
        previous_version: 1,
        created_at: "2026-07-23T11:00:00Z",
      },
    ]);
    vi.mocked(regionalService.exportConfiguration).mockResolvedValue(exported);
    vi.mocked(regionalService.importConfiguration).mockResolvedValue({
      ...configurationFixture(),
      version: 3,
      document: exported.document,
    });
    vi.mocked(regionalService.rollbackConfiguration).mockResolvedValue({
      ...configurationFixture(),
      version: 4,
      document: exported.document,
    });
    const createObjectURL = vi.fn(() => "blob:regional-config");
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

    const { container } = renderPage();
    expect(await screen.findByText("Version 1 · update")).toBeInTheDocument();
    expect(screen.getByText(/corr-history-1/iu)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Export JSON" }));
    await waitFor(() =>
      expect(regionalService.exportConfiguration).toHaveBeenCalledWith("development")
    );
    expect(createObjectURL).toHaveBeenCalled();

    const importedDocument = {
      ...exported.document,
      resource: { ...exported.document.resource, name_default: "Imported resource" },
    };
    const input = container.querySelector('input[type="file"]');
    if (!(input instanceof HTMLInputElement)) throw new Error("Import input was not rendered.");
    const file = new File(
      [JSON.stringify({ document: importedDocument })],
      "regional-config.json",
      {
        type: "application/json",
      }
    );
    Object.defineProperty(file, "text", {
      configurable: true,
      value: vi.fn().mockResolvedValue(JSON.stringify({ document: importedDocument })),
    });
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() =>
      expect(regionalService.importConfiguration).toHaveBeenCalledWith(
        "development",
        importedDocument
      )
    );

    await user.click(screen.getAllByRole("button", { name: "Rollback" })[1]!);
    await user.click(await screen.findByRole("button", { name: "Create rollback version" }));
    await waitFor(() =>
      expect(regionalService.rollbackConfiguration).toHaveBeenCalledWith("development", 2)
    );
  });

  it("updates typed controls and blocks invalid local policy before mutations", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("Resource defaults and safe limits")).toBeInTheDocument();
    await user.click(screen.getByLabelText("Capability enabled for this environment"));
    await user.click(screen.getByLabelText("tenant_admin"));
    await user.clear(screen.getByLabelText("Cohorts"));
    await user.type(screen.getByLabelText("Cohorts"), "pilot, regulated, pilot");
    await user.clear(screen.getByLabelText("Minimum name length"));
    await user.type(screen.getByLabelText("Minimum name length"), "65");
    await user.clear(screen.getByLabelText("Maximum name length"));
    await user.type(screen.getByLabelText("Maximum name length"), "64");
    await user.clear(screen.getByLabelText("Default name"));
    await user.type(screen.getByLabelText("Default name"), "R");
    await user.clear(screen.getByLabelText("Description limit"));
    await user.type(screen.getByLabelText("Description limit"), "10001");
    await user.clear(screen.getByLabelText("Compliance tag limit"));
    await user.type(screen.getByLabelText("Compliance tag limit"), "101");
    await user.clear(screen.getByLabelText("Configuration byte limit"));
    await user.type(screen.getByLabelText("Configuration byte limit"), "127");
    fireEvent.change(screen.getByLabelText("Default country code"), {
      target: { value: "USA" },
    });
    await user.clear(screen.getByLabelText("Default page size"));
    await user.type(screen.getByLabelText("Default page size"), "600");
    await user.clear(screen.getByLabelText("Maximum page size"));
    await user.type(screen.getByLabelText("Maximum page size"), "500");
    await user.clear(screen.getByLabelText("Cache probe TTL (seconds)"));
    await user.type(screen.getByLabelText("Cache probe TTL (seconds)"), "301");

    expect(screen.getByText("Minimum name length must be between 1 and 64.")).toBeInTheDocument();
    expect(
      screen.getByText("Maximum name length must be at least the minimum and no greater than 512.")
    ).toBeInTheDocument();
    expect(screen.getByText("Description limit must be between 0 and 10,000.")).toBeInTheDocument();
    expect(screen.getByText("Compliance tag limit must be between 0 and 100.")).toBeInTheDocument();
    expect(
      screen.getByText("Configuration size must be between 128 and 65,536 bytes.")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Default country code must contain exactly two letters.")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Default page size must be positive and no greater than the maximum.")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Cache probe TTL must be between 1 and 300 seconds.")
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Apply version" })).toBeDisabled();
    expect(regionalService.previewConfiguration).not.toHaveBeenCalled();
    expect(regionalService.updateConfiguration).not.toHaveBeenCalled();
  });

  it("validates disabled defaults, malformed imports, empty history, and history retry state", async () => {
    const user = userEvent.setup();
    const document = configurationFixture().document;
    vi.mocked(regionalService.listConfigurationHistory).mockResolvedValueOnce([]);

    const { container, unmount } = renderPage();
    expect(
      await screen.findByText("No prior versions exist for this environment.")
    ).toBeInTheDocument();

    await user.click(screen.getByLabelText("country_code"));
    expect(screen.getByLabelText("Default country code")).toBeDisabled();
    await user.click(screen.getByLabelText("jurisdiction_type"));
    expect(screen.getByLabelText("Default jurisdiction type")).toBeDisabled();
    await user.click(screen.getByLabelText("compliance_tags"));
    expect(screen.getByLabelText("Default compliance tags")).toBeDisabled();

    const input = container.querySelector('input[type="file"]');
    if (!(input instanceof HTMLInputElement)) throw new Error("Import input was not rendered.");
    const file = new File(["not-json"], "regional-config.json", {
      type: "application/json",
    });
    Object.defineProperty(file, "text", {
      configurable: true,
      value: vi.fn().mockResolvedValue("not-json"),
    });
    fireEvent.change(input, { target: { files: [file] } });
    expect(await screen.findByRole("alert")).toHaveTextContent(/JSON/u);
    expect(regionalService.importConfiguration).not.toHaveBeenCalled();
    unmount();

    vi.mocked(regionalService.listConfigurationHistory).mockRejectedValue(
      new Error("history down")
    );
    vi.mocked(regionalService.previewConfiguration).mockRejectedValue(
      new Error("preview rejected")
    );
    renderPage();
    expect(
      await screen.findByText("Configuration history could not be loaded.")
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Preview" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("preview rejected");

    fireEvent.change(screen.getByLabelText("Complete configuration document"), {
      target: { value: JSON.stringify({ ...document, resource: undefined }) },
    });
    await user.click(screen.getByRole("button", { name: "Validate and stage JSON" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The document is missing one or more required configuration fields."
    );
  });
});
