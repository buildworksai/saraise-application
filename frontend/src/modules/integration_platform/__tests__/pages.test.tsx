/* eslint-disable max-lines-per-function -- integration page coverage intentionally exercises routed workflows end to end. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/api-client";
import {
  CredentialMetadataPage,
  CreateCredentialPage,
  CreateIntegrationPage,
  EditIntegrationPage,
  IntegrationDetailPage,
  IntegrationListPage,
  RotateCredentialPage,
} from "../pages/IntegrationPages";
import { ConfigurationPage } from "../pages/ConfigurationPage";
import { ConnectorCatalogPage, ConnectorDetailPage } from "../pages/ConnectorPages";
import { DeliveryDetailPage, DeliveryListPage } from "../pages/DeliveryPages";
import { CreateMappingPage, MappingDetailPage, MappingListPage } from "../pages/MappingPages";
import {
  CreateWebhookPage,
  EditWebhookPage,
  WebhookDetailPage,
  WebhookListPage,
} from "../pages/WebhookPages";

const calls = vi.hoisted(() => ({
  activateIntegration: vi.fn(),
  activateWebhook: vi.fn(),
  createCredential: vi.fn(),
  createIntegration: vi.fn(),
  createMapping: vi.fn(),
  createWebhook: vi.fn(),
  deactivateIntegration: vi.fn(),
  deactivateWebhook: vi.fn(),
  deleteDelivery: vi.fn(),
  deleteIntegration: vi.fn(),
  deleteMapping: vi.fn(),
  deleteWebhook: vi.fn(),
  exportConfiguration: vi.fn(),
  getConfiguration: vi.fn(),
  getConnector: vi.fn(),
  getConnectorHealth: vi.fn(),
  getConnectorSchema: vi.fn(),
  getDelivery: vi.fn(),
  getCredential: vi.fn(),
  getIntegration: vi.fn(),
  getManageCapability: vi.fn(),
  getMapping: vi.fn(),
  getWebhook: vi.fn(),
  importConfiguration: vi.fn(),
  listConfigurationAudits: vi.fn(),
  listConfigurationVersions: vi.fn(),
  listConnectors: vi.fn(),
  listCredentials: vi.fn(),
  listDeliveries: vi.fn(),
  listIntegrations: vi.fn(),
  listMappings: vi.fn(),
  listWebhooks: vi.fn(),
  previewConfiguration: vi.fn(),
  previewMappings: vi.fn(),
  redriveDelivery: vi.fn(),
  revokeCredential: vi.fn(),
  rollbackConfiguration: vi.fn(),
  rotateCredential: vi.fn(),
  rotateWebhookSecret: vi.fn(),
  saveConfiguration: vi.fn(),
  syncIntegration: vi.fn(),
  testIntegration: vi.fn(),
  updateIntegration: vi.fn(),
  updateMapping: vi.fn(),
  updateWebhook: vi.fn(),
  validateMappings: vi.fn(),
}));
vi.mock("../services/integration-platform-service", () => ({ integrationPlatformService: calls }));

const meta = {
  correlation_id: "corr-page",
  timestamp: "2026-07-22T00:00:00Z",
  count: 0,
  page: 1,
  page_size: 25,
  total_pages: 0,
  has_next: false,
  has_previous: false,
};
const configDocument = {
  schema_version: 1,
  environment: "development",
  adapter: {
    spi_version: "1",
    capabilities: ["test", "pull", "push", "receive", "deliver"],
    adapter_key_max_length: 80,
    cursor_max_length: 255,
  },
  transformations: {
    operations: ["rename", "trim", "string_case", "number", "date_format", "default", "enum_map"],
    string_case_modes: ["upper", "lower"],
    number_modes: ["integer"],
    default_number_mode: "integer",
    default_input_date_format: "iso",
    allow_unmapped_enum: false,
    max_chain_length: 3,
  },
  validation: {
    name_max_length: 120,
    description_max_length: 500,
    credential_max_length: 128,
    url_max_length: 500,
    event_name_pattern: "^[a-z.]+$",
    event_name_max_length: 64,
    nonce_max_length: 64,
    signature_max_length: 128,
    error_code_max_length: 64,
  },
  security: {
    connector_access_policy: "explicit_entitlement",
    secret_field_names: ["token"],
    signature_window_seconds: 300,
    payload_max_bytes: 65536,
    credential_hint_characters: 4,
    signing_secret_bytes: 32,
    outbound_nonce_bytes: 16,
    diagnostic_fields: ["status"],
  },
  webhooks: {
    timeout_seconds_default: 10,
    timeout_seconds_min: 1,
    timeout_seconds_max: 30,
    max_attempts_default: 3,
    max_attempts_min: 1,
    max_attempts_max: 10,
    success_status_min: 200,
    success_status_max: 299,
    retry_statuses: [429],
    retry_server_error_min: 500,
    retry_delay_max_seconds: 60,
    connect_timeout_max_seconds: 5,
    http_client_retries: 2,
    inbound_rate: "60/min",
  },
  synchronization: {
    directions: ["pull", "push"],
    active_statuses: ["active"],
    pull_batch_limit: 500,
    quota_cost: 1,
  },
  workflows: {
    integration_delete_statuses: ["inactive", "error"],
    integration_activation_statuses: ["inactive"],
    activation_requires_successful_test: true,
    integration_transitions: { inactive: ["activate"], active: ["deactivate"] },
    credential_transitions: { active: ["revoke"] },
    webhook_transitions: { inactive: ["activate"], active: ["deactivate"] },
    delivery_transitions: { dead_letter: ["redrive"] },
  },
  jobs: { poll_after_ms: 1000, progress_min: 0, progress_max: 100, terminal_progress: 100 },
  list: {
    page_size: 25,
    connector_page_size: 50,
    refresh_interval_ms: 30000,
    active_delivery_poll_ms: 5000,
    integration_poll_ms: 5000,
    integration_ordering: "-updated_at",
    integration_ordering_fields: ["name", "-updated_at"],
    webhook_ordering: "-updated_at",
    webhook_ordering_fields: ["name"],
    delivery_ordering: "-created_at",
    mapping_ordering: "position",
    mapping_ordering_fields: ["position"],
  },
  quotas: { sync_jobs: 100 },
  mapping: { default_position: 0, default_required: false, preview_record_limit: 5 },
  health: { probe_timeout_seconds: 3, broker_acknowledgement_seconds: 2 },
  feature_flags: { push_synchronization: { enabled: true, roles: [], cohorts: [] } },
  navigation: {
    base_order: 10,
    route_order: {},
    status_positive: ["active", "available", "delivered", "healthy", "closed", "succeeded"],
    status_warning: ["testing", "retrying", "locked"],
    status_danger: ["error", "dead_letter", "unavailable", "failed"],
  },
} as const;

const configuration = {
  id: "config-id",
  tenant_id: "tenant-id",
  environment: "development",
  version: 2,
  document: configDocument,
  updated_at: "2026-07-22T00:00:00Z",
  updated_by: "operator-id",
};

const connector = {
  id: "11111111-1111-4111-8111-111111111111",
  key: "crm",
  name: "CRM connector",
  connector_type: "api",
  adapter_key: "crm.adapter",
  version: "1.0.0",
  capabilities: ["test", "pull", "push"],
  module_id: "crm",
  access_policy: "entitlement_required",
  required_entitlement: "crm.integration",
  is_active: true,
  is_entitled: true,
  entitlement_reason: undefined,
  adapter_available: true,
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-22T00:00:00Z",
} as const;

const schema = {
  connector_id: connector.id,
  config_schema: {
    type: "object",
    required: ["base_url"],
    properties: {
      base_url: { type: "string", title: "Base URL", description: "Tenant CRM endpoint." },
      sandbox: { type: "boolean", title: "Sandbox" },
    },
  },
  credential_schema: { type: "object", properties: { api_key: { type: "string", secret: true } } },
} as const;

function renderPage(path = "/integration-platform") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <IntegrationListPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function renderWithRoute(element: React.ReactElement, path: string, route = path) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={route} element={element} />
          <Route path="*" element={<div>navigated</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("IntegrationListPage governed states", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("crypto", { randomUUID: () => "operation-id" });
    vi.stubGlobal(
      "confirm",
      vi.fn(() => true)
    );
    vi.stubGlobal(
      "prompt",
      vi.fn(() => "Warehouse sync")
    );
    calls.getConfiguration.mockResolvedValue(configuration);
    calls.getManageCapability.mockResolvedValue({
      allowed: true,
      permission: "integration_platform.manage",
      reason_code: "allowed",
    });
    calls.listConnectors.mockResolvedValue({ items: [], meta });
    calls.listCredentials.mockResolvedValue([]);
    calls.listMappings.mockResolvedValue({ items: [], meta });
  });

  it("renders a layout-preserving loading skeleton", () => {
    calls.listIntegrations.mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByLabelText("Loading integrations")).toHaveAttribute("aria-busy", "true");
  });

  it("distinguishes first-use empty and filtered-empty with reset", async () => {
    calls.listIntegrations.mockResolvedValue({ items: [], meta });
    const first = renderPage();
    expect(await screen.findByText("integrations")).toBeInTheDocument();
    first.unmount();
    renderPage("/integration-platform?status=active");
    expect(await screen.findByText("No matching integrations")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reset filters" }));
    await waitFor(() => expect(calls.listIntegrations).toHaveBeenCalledTimes(3));
  });

  it("renders explicit 403 and correlation-aware retry behavior", async () => {
    calls.listIntegrations
      .mockRejectedValueOnce(new ApiError("Denied", 403, undefined, "policy_denied", "corr-denied"))
      .mockResolvedValueOnce({ items: [], meta });
    renderPage();
    expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument();
    expect(screen.getByText(/corr-denied/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("integrations")).toBeInTheDocument();
  });

  it("renders explicit tenant-safe 404 state", async () => {
    calls.listIntegrations.mockRejectedValue(
      new ApiError("Missing", 404, undefined, "not_found", "corr-missing")
    );
    renderPage();
    expect(await screen.findByRole("heading", { name: "Record not found" })).toBeInTheDocument();
  });

  it("applies connector, mapping, and webhook list filters through governed query payloads", async () => {
    calls.listConnectors.mockResolvedValue({ items: [connector], meta: { ...meta, count: 1 } });
    calls.listMappings.mockResolvedValue({
      items: [
        {
          id: "mapping-id",
          integration_id: "integration-id",
          integration_name: "Warehouse sync",
          name: "Email mapping",
          source_field: "email",
          target_field: "contact.email",
          transform: { operation: "rename" },
          position: 0,
          is_required: true,
          default_value: null,
          created_at: "2026-07-22T00:00:00Z",
          updated_at: "2026-07-22T00:00:00Z",
        },
      ],
      meta: { ...meta, count: 1 },
    });
    calls.listWebhooks.mockResolvedValue({
      items: [
        {
          id: "webhook-id",
          name: "Outbound CRM",
          direction: "outbound",
          url: "https://events.example.test",
          public_id: "public-id",
          events: ["lead.created"],
          status: "active",
          timeout_seconds: 10,
          max_attempts: 3,
          last_received_at: null,
          last_delivered_at: "2026-07-22T00:00:00Z",
          last_error_code: "",
          created_at: "2026-07-22T00:00:00Z",
          updated_at: "2026-07-22T00:00:00Z",
          config: {},
        },
      ],
      meta: { ...meta, count: 1 },
    });

    const catalog = renderWithRoute(
      <ConnectorCatalogPage />,
      "/integration-platform/connectors?active=false&type=api",
      "/integration-platform/connectors"
    );
    expect(await screen.findByText("CRM connector")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Search connectors"), "crm");
    await userEvent.keyboard("{Enter}");
    await waitFor(() =>
      expect(calls.listConnectors).toHaveBeenLastCalledWith(
        expect.objectContaining({ connector_type: "api", is_active: false, search: "crm" })
      )
    );
    catalog.unmount();

    const mappings = renderWithRoute(
      <MappingListPage />,
      "/integration-platform/mappings?integration=integration-id&source=email",
      "/integration-platform/mappings"
    );
    expect(await screen.findByText("Email mapping")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Filter target field"), "contact.email");
    await waitFor(() =>
      expect(calls.listMappings).toHaveBeenLastCalledWith(
        expect.objectContaining({
          integration_id: "integration-id",
          source_field: "email",
          target_field: "contact.email",
        })
      )
    );
    mappings.unmount();

    renderWithRoute(
      <WebhookListPage />,
      "/integration-platform/webhooks?direction=outbound&status=active",
      "/integration-platform/webhooks"
    );
    expect(await screen.findByText("Outbound CRM")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Filter subscribed event"), "lead.created");
    await waitFor(() =>
      expect(calls.listWebhooks).toHaveBeenLastCalledWith(
        expect.objectContaining({
          direction: "outbound",
          status: "active",
          event: "lead.created",
        })
      )
    );
  });

  it("submits server search and supports keyboard operation", async () => {
    calls.listIntegrations.mockResolvedValue({ items: [], meta });
    renderPage();
    const search = await screen.findByRole("textbox", { name: "Search integrations" });
    fireEvent.change(search, { target: { value: "warehouse" } });
    search.focus();
    await userEvent.keyboard("{Enter}");
    await waitFor(() =>
      expect(calls.listIntegrations).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: "warehouse" })
      )
    );
  });

  it("creates an integration with schema configuration, credential write, and queued test", async () => {
    calls.listConnectors.mockResolvedValue({ items: [connector], meta: { ...meta, count: 1 } });
    calls.getConnectorSchema.mockResolvedValue(schema);
    calls.createIntegration.mockResolvedValue({
      ...connector,
      id: "22222222-2222-4222-8222-222222222222",
      connector_id: connector.id,
      connector_name: connector.name,
      name: "Warehouse sync",
      description: "Nightly pull",
      integration_type: "api",
      status: "inactive",
      last_tested_at: null,
      last_test_job_id: null,
      last_sync_job_id: null,
      last_error_code: "",
      last_error_message: "",
      credentials_count: 1,
      mappings_count: 0,
      config: { base_url: "https://crm.example.test", sandbox: true },
      transition_history: [],
      latest_test_evidence: null,
      latest_sync_evidence: null,
    });
    calls.createCredential.mockResolvedValue({
      id: "cred-id",
      integration_id: "22222222-2222-4222-8222-222222222222",
      credential_type: "api_key",
      display_hint: "last4",
      version: 1,
      status: "active",
      expires_at: null,
      rotated_at: null,
      revoked_at: null,
      created_at: "2026-07-22T00:00:00Z",
    });
    calls.testIntegration.mockResolvedValue({
      job_id: "job-id",
      status: "queued",
      correlation_id: "corr-test",
      accepted_at: "2026-07-22T00:00:00Z",
      poll_after_ms: 1000,
    });

    renderWithRoute(<CreateIntegrationPage />, "/integration-platform/new");
    await userEvent.click(await screen.findByRole("button", { name: /CRM connector/iu }));
    await userEvent.type(await screen.findByLabelText(/Base URL/iu), "https://crm.example.test");
    await userEvent.type(screen.getByLabelText("Integration name"), "Warehouse sync");
    await userEvent.type(screen.getByLabelText("Description"), "Nightly pull");
    await userEvent.type(screen.getByLabelText("Credential value"), "secret-token");
    await userEvent.click(screen.getByRole("button", { name: "Create & test connection" }));

    await waitFor(() => expect(calls.createIntegration).toHaveBeenCalled());
    expect(calls.createIntegration.mock.calls[0]?.[0]).toMatchObject({
      connector_id: connector.id,
      config: { base_url: "https://crm.example.test" },
      name: "Warehouse sync",
    });
    expect(calls.createCredential).toHaveBeenCalledWith("22222222-2222-4222-8222-222222222222", {
      credential_type: "api_key",
      plaintext: "secret-token",
    });
    expect(calls.testIntegration).toHaveBeenCalledWith("22222222-2222-4222-8222-222222222222", {
      idempotency_key: "setup-test-operation-id",
    });
  });

  it("fails closed when connector schema cannot load and retries without creating resources", async () => {
    calls.listConnectors.mockResolvedValue({ items: [connector], meta: { ...meta, count: 1 } });
    calls.getConnectorSchema
      .mockRejectedValueOnce(
        new ApiError("Schema unavailable", 503, undefined, "SCHEMA_DOWN", "corr-schema")
      )
      .mockResolvedValueOnce(schema);

    renderWithRoute(<CreateIntegrationPage />, "/integration-platform/new");
    await userEvent.click(await screen.findByRole("button", { name: /CRM connector/iu }));

    expect(
      await screen.findByRole("heading", { name: "Integration Platform is unavailable" })
    ).toBeInTheDocument();
    expect(screen.getByText(/corr-schema/iu)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create & test connection" })).toBeDisabled();
    expect(calls.createIntegration).not.toHaveBeenCalled();
    expect(calls.testIntegration).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByLabelText(/Base URL/iu)).toBeInTheDocument();
  });

  it("blocks setup submission when required non-secret connector configuration is missing", async () => {
    calls.listConnectors.mockResolvedValue({ items: [connector], meta: { ...meta, count: 1 } });
    calls.getConnectorSchema.mockResolvedValue(schema);

    renderWithRoute(<CreateIntegrationPage />, "/integration-platform/new");
    await userEvent.click(await screen.findByRole("button", { name: /CRM connector/iu }));
    const baseUrl = await screen.findByLabelText(/Base URL/iu);
    await userEvent.type(screen.getByLabelText("Integration name"), "Warehouse sync");

    expect(baseUrl).toBeInvalid();
    await userEvent.click(screen.getByRole("button", { name: "Create & test connection" }));

    expect(calls.createIntegration).not.toHaveBeenCalled();
    expect(calls.createCredential).not.toHaveBeenCalled();
    expect(calls.testIntegration).not.toHaveBeenCalled();
  });

  it("runs detail page actions through configured sync direction and deletion confirmation", async () => {
    calls.getIntegration.mockResolvedValue({
      id: "33333333-3333-4333-8333-333333333333",
      connector_id: connector.id,
      connector_name: connector.name,
      name: "Warehouse sync",
      description: "Nightly pull",
      integration_type: "api",
      status: "active",
      last_tested_at: null,
      last_test_job_id: null,
      last_sync_job_id: null,
      last_error_code: "",
      last_error_message: "",
      credentials_count: 0,
      mappings_count: 1,
      created_at: "2026-07-22T00:00:00Z",
      updated_at: "2026-07-22T00:00:00Z",
      config: { base_url: "https://crm.example.test" },
      transition_history: [],
      latest_test_evidence: null,
      latest_sync_evidence: null,
    });
    calls.listMappings.mockResolvedValue({
      items: [
        {
          id: "map-id",
          integration_id: "33333333-3333-4333-8333-333333333333",
          integration_name: "Warehouse sync",
          name: "Email",
          source_field: "email",
          target_field: "email",
          transform: { operation: "rename" },
          position: 0,
          is_required: true,
          default_value: null,
          created_at: "2026-07-22T00:00:00Z",
          updated_at: "2026-07-22T00:00:00Z",
        },
      ],
      meta: { ...meta, count: 1 },
    });
    calls.syncIntegration.mockResolvedValue({
      job_id: "sync-job",
      status: "queued",
      correlation_id: "corr-sync",
      accepted_at: "2026-07-22T00:00:00Z",
      poll_after_ms: 1000,
    });
    calls.deactivateIntegration.mockResolvedValue({});

    renderWithRoute(
      <IntegrationDetailPage />,
      "/integration-platform/33333333-3333-4333-8333-333333333333",
      "/integration-platform/:id"
    );
    await userEvent.selectOptions(
      await screen.findByLabelText("Synchronization direction"),
      "push"
    );
    await userEvent.click(screen.getByRole("button", { name: /Sync/iu }));
    await waitFor(() =>
      expect(calls.syncIntegration).toHaveBeenCalledWith(
        "33333333-3333-4333-8333-333333333333",
        expect.objectContaining({ direction: "push", mapping_ids: ["map-id"] })
      )
    );
    await userEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    expect(calls.deactivateIntegration).toHaveBeenCalledWith(
      "33333333-3333-4333-8333-333333333333",
      { transition_key: "deactivate-operation-id" }
    );
  });

  it("creates a webhook only after direction-aware validation and shows the one-time secret", async () => {
    calls.createWebhook.mockResolvedValue({
      signing_secret: "whsec_once", // pragma: allowlist secret
      shown_once: true,
      webhook: {
        id: "webhook-id",
        name: "Outbound CRM",
        direction: "outbound",
        url: "https://events.example.test",
        public_id: "public-id",
        events: ["lead.created"],
        status: "inactive",
        timeout_seconds: 10,
        max_attempts: 3,
        last_received_at: null,
        last_delivered_at: null,
        last_error_code: "",
        created_at: "2026-07-22T00:00:00Z",
        updated_at: "2026-07-22T00:00:00Z",
        config: {},
        transition_history: [],
        delivery_summary: {
          queued: 0,
          retrying: 0,
          delivered: 0,
          dead_letter: 0,
          success_rate: null,
        },
      },
    });
    renderWithRoute(<CreateWebhookPage />, "/integration-platform/webhooks/new");
    await userEvent.selectOptions(await screen.findByLabelText("Direction"), "outbound");
    await userEvent.type(screen.getByLabelText("Name"), "Outbound CRM");
    await userEvent.type(screen.getByLabelText("Destination URL"), "https://events.example.test");
    await userEvent.type(
      screen.getByLabelText("Subscribed events (comma-separated)"),
      "lead.created"
    );
    fireEvent.change(screen.getByLabelText("Non-secret configuration (JSON)"), {
      target: { value: '{"tier":"gold"}' },
    });
    await userEvent.click(screen.getByRole("button", { name: "Create webhook" }));
    expect(await screen.findByDisplayValue("whsec_once")).toBeInTheDocument();
    expect(calls.createWebhook).toHaveBeenCalledWith(
      expect.objectContaining({ direction: "outbound", events: ["lead.created"] })
    );
  });

  it("rotates a webhook secret and renders inbound signing guidance", async () => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn() } });
    calls.getWebhook.mockResolvedValue({
      id: "webhook-id",
      name: "Inbound orders",
      direction: "inbound",
      url: "",
      public_id: "public-id",
      events: ["order.created"],
      status: "active",
      timeout_seconds: 10,
      max_attempts: 3,
      last_received_at: "2026-07-22T00:00:00Z",
      last_delivered_at: null,
      last_error_code: "",
      created_at: "2026-07-22T00:00:00Z",
      updated_at: "2026-07-22T00:00:00Z",
      config: {},
      transition_history: [],
      delivery_summary: { queued: 1, retrying: 0, delivered: 4, dead_letter: 0, success_rate: 80 },
    });
    calls.rotateWebhookSecret.mockResolvedValue({
      signing_secret: "rotated-secret", // pragma: allowlist secret
      shown_once: true,
    });
    renderWithRoute(
      <WebhookDetailPage />,
      "/integration-platform/webhooks/webhook-id",
      "/integration-platform/webhooks/:id"
    );
    expect(
      await screen.findByText("POST /api/v2/integration-platform/webhooks/inbound/public-id/")
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Rotate secret/iu }));
    expect(await screen.findByLabelText("New signing secret")).toHaveValue("rotated-secret");
  });

  it("edits an inbound webhook using the loaded disabled direction instead of an empty form field", async () => {
    calls.getWebhook.mockResolvedValue({
      id: "webhook-id",
      name: "Inbound orders",
      direction: "inbound",
      url: "",
      public_id: "public-id",
      events: ["order.created"],
      status: "inactive",
      timeout_seconds: 10,
      max_attempts: 3,
      last_received_at: null,
      last_delivered_at: null,
      last_error_code: "",
      created_at: "2026-07-22T00:00:00Z",
      updated_at: "2026-07-22T00:00:00Z",
      config: { tier: "gold" },
      transition_history: [],
      delivery_summary: {
        queued: 0,
        retrying: 0,
        delivered: 0,
        dead_letter: 0,
        success_rate: null,
      },
    });
    calls.updateWebhook.mockResolvedValue({
      id: "webhook-id",
      name: "Inbound order stream",
      direction: "inbound",
      url: "",
      public_id: "public-id",
      events: ["order.created"],
      status: "inactive",
      timeout_seconds: 10,
      max_attempts: 3,
      last_received_at: null,
      last_delivered_at: null,
      last_error_code: "",
      created_at: "2026-07-22T00:00:00Z",
      updated_at: "2026-07-23T00:00:00Z",
      config: { tier: "gold" },
      transition_history: [],
      delivery_summary: {
        queued: 0,
        retrying: 0,
        delivered: 0,
        dead_letter: 0,
        success_rate: null,
      },
    });

    renderWithRoute(
      <EditWebhookPage />,
      "/integration-platform/webhooks/webhook-id/edit",
      "/integration-platform/webhooks/:id/edit"
    );
    const direction = await screen.findByLabelText("Direction");
    expect(direction).toBeDisabled();
    const name = screen.getByLabelText("Name");
    await userEvent.clear(name);
    await userEvent.type(name, "Inbound order stream");
    await userEvent.click(screen.getByRole("button", { name: "Save webhook" }));

    await waitFor(() =>
      expect(calls.updateWebhook).toHaveBeenCalledWith("webhook-id", {
        name: "Inbound order stream",
        direction: "inbound",
        url: undefined,
        events: ["order.created"],
        config: { tier: "gold" },
        timeout_seconds: 10,
        max_attempts: 3,
      })
    );
  });

  it("validates, saves, and previews a mapping through the governed endpoints", async () => {
    calls.validateMappings.mockResolvedValue({ valid: true, errors: [], mapping_count: 1 });
    calls.createMapping.mockResolvedValue({
      id: "mapping-id",
      integration_id: "44444444-4444-4444-8444-444444444444",
      integration_name: "Warehouse sync",
      name: "Email mapping",
      source_field: "email",
      target_field: "contact.email",
      transform: { operation: "trim", options: {} },
      position: 0,
      is_required: true,
      default_value: null,
      created_at: "2026-07-22T00:00:00Z",
      updated_at: "2026-07-22T00:00:00Z",
    });
    calls.previewMappings.mockResolvedValue({
      records: [{ "contact.email": "a@example.com" }],
      failures: [],
    });
    renderWithRoute(<CreateMappingPage />, "/integration-platform/mappings/new");
    await userEvent.type(
      await screen.findByLabelText("Integration ID"),
      "44444444-4444-4444-8444-444444444444"
    );
    await userEvent.type(screen.getByLabelText("Source field"), "email");
    await userEvent.type(screen.getByLabelText("Mapping name"), "Email mapping");
    await userEvent.type(screen.getByLabelText("Target field"), "contact.email");
    await userEvent.selectOptions(screen.getByLabelText("Operation"), "trim");
    await userEvent.click(screen.getByLabelText("Source field is required"));
    fireEvent.change(screen.getByLabelText("Sample record (JSON object)"), {
      target: { value: '{"email":" a@example.com "}' },
    });
    await userEvent.click(screen.getByRole("button", { name: /Validate, save & preview/iu }));
    expect(await screen.findByText("Server-side field validation passed")).toBeInTheDocument();
    expect(calls.validateMappings).toHaveBeenCalledWith(
      expect.objectContaining({ mappings: [expect.objectContaining({ is_required: true })] })
    );
    expect(screen.getByLabelText("Transformed records, redacted evidence")).toHaveTextContent(
      "contact.email"
    );
  });

  it("runs mapping detail preview and delete actions against loaded mapping evidence", async () => {
    calls.getMapping.mockResolvedValue({
      id: "mapping-id",
      integration_id: "44444444-4444-4444-8444-444444444444",
      integration_name: "Warehouse sync",
      name: "Email mapping",
      source_field: "email",
      target_field: "contact.email",
      transform: { operation: "rename" },
      position: 2,
      is_required: false,
      default_value: null,
      created_at: "2026-07-22T00:00:00Z",
      updated_at: "2026-07-22T00:00:00Z",
    });
    calls.previewMappings.mockResolvedValue({
      records: [],
      failures: [
        {
          record_index: 0,
          mapping_id: "mapping-id",
          source_field: "email",
          target_field: "contact.email",
          code: "missing",
          message: "email missing",
        },
      ],
    });
    calls.deleteMapping.mockResolvedValue(undefined);
    renderWithRoute(
      <MappingDetailPage />,
      "/integration-platform/mappings/mapping-id",
      "/integration-platform/mappings/:id"
    );
    await userEvent.click(await screen.findByRole("button", { name: /Run preview/iu }));
    expect(await screen.findByText(/email missing/iu)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Delete/iu }));
    expect(calls.deleteMapping).toHaveBeenCalledWith("mapping-id");
  });

  it("renders connector detail availability from entitlement, adapter, health, and schema evidence", async () => {
    calls.getConnector.mockResolvedValue({
      ...connector,
      is_entitled: false,
      entitlement_reason: "Requires CRM entitlement",
      schema: schema.config_schema,
      credential_schema: schema.credential_schema,
    });
    calls.getConnectorHealth.mockResolvedValue({
      connector_id: connector.id,
      status: "degraded",
      adapter_registered: true,
      circuit_state: "half_open",
      checked_at: "2026-07-22T00:00:00Z",
      reason: "recent timeout",
      correlation_id: "corr-health",
    });
    renderWithRoute(
      <ConnectorDetailPage />,
      `/integration-platform/connectors/${connector.id}`,
      "/integration-platform/connectors/:id"
    );
    expect(await screen.findByText("Requires CRM entitlement")).toBeInTheDocument();
    expect(screen.getByText("corr-health")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View required module" })).toBeInTheDocument();
  });

  it("redrives only dead-letter delivery evidence and surfaces durable job correlation", async () => {
    calls.getDelivery.mockResolvedValue({
      id: "delivery-id",
      webhook_id: "webhook-id",
      webhook_name: "Outbound CRM",
      event: "lead.created",
      status: "dead_letter",
      attempt_count: 3,
      max_attempts: 3,
      next_attempt_at: null,
      response_code: null,
      error_code: "HTTP_503",
      duration_ms: null,
      job_id: "job-dead",
      correlation_id: "corr-dead",
      delivered_at: null,
      created_at: "2026-07-22T00:00:00Z",
      updated_at: "2026-07-22T00:00:00Z",
      payload: { lead: "redacted" },
      payload_hash: "hash",
      idempotency_key: "idem",
      error_message: "provider unavailable",
      transition_history: [
        {
          transition: "deliver",
          from_status: "retrying",
          to_status: "dead_letter",
          occurred_at: "2026-07-22T00:00:00Z",
          transition_key: "dead-lettered",
        },
      ],
      attempts: [],
    });
    calls.redriveDelivery.mockResolvedValue({
      job_id: "job-redrive",
      status: "queued",
      correlation_id: "corr-redrive",
      accepted_at: "2026-07-22T00:00:00Z",
      poll_after_ms: 1000,
    });
    renderWithRoute(
      <DeliveryDetailPage />,
      "/integration-platform/deliveries/delivery-id",
      "/integration-platform/deliveries/:id"
    );
    await userEvent.click(await screen.findByRole("button", { name: /Redrive/iu }));
    expect(await screen.findByText(/corr-redrive/iu)).toBeInTheDocument();
    expect(calls.redriveDelivery).toHaveBeenCalledWith("delivery-id", {
      transition_key: "redrive-operation-id",
    });
  });

  it("applies delivery list filters, renders retry evidence, and navigates to delivery detail", async () => {
    calls.listDeliveries.mockResolvedValue({
      items: [
        {
          id: "delivery-id",
          webhook_id: "webhook-id",
          webhook_name: "Outbound CRM",
          event: "lead.created",
          status: "retrying",
          attempt_count: 2,
          max_attempts: 5,
          next_attempt_at: "2026-07-22T10:10:00Z",
          response_code: 503,
          error_code: "HTTP_503",
          duration_ms: 1400,
          job_id: "delivery-job",
          correlation_id: "corr-retry",
          delivered_at: null,
          created_at: "2026-07-22T10:00:00Z",
          updated_at: "2026-07-22T10:05:00Z",
        },
      ],
      meta: { ...meta, count: 1, total_pages: 1 },
    });

    renderWithRoute(
      <DeliveryListPage />,
      "/integration-platform/deliveries?webhook=webhook-id&status=retrying&after=2026-07-22T10%3A00",
      "/integration-platform/deliveries"
    );

    expect(await screen.findByRole("link", { name: "lead.created" })).toBeInTheDocument();
    expect(screen.getByText("corr-retry")).toBeInTheDocument();
    expect(screen.getByText("2/5")).toBeInTheDocument();
    await waitFor(() =>
      expect(calls.listDeliveries).toHaveBeenCalledWith(
        expect.objectContaining({
          webhook_id: "webhook-id",
          status: "retrying",
          created_after: "2026-07-22T10:00",
        })
      )
    );

    fireEvent.change(screen.getByLabelText("Created before"), {
      target: { value: "2026-07-22T11:00" },
    });
    await userEvent.type(screen.getByLabelText("Filter delivery event"), "lead.created");
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() =>
      expect(calls.listDeliveries).toHaveBeenLastCalledWith(
        expect.objectContaining({
          created_before: "2026-07-22T11:00",
          event: "lead.created",
          status: "retrying",
          webhook_id: "webhook-id",
        })
      )
    );

    await userEvent.click(screen.getByRole("link", { name: "lead.created" }));
    expect(await screen.findByText("navigated")).toBeInTheDocument();
  });

  it("keeps redrive disabled for non-dead-letter deliveries while preserving failure evidence", async () => {
    calls.getDelivery.mockResolvedValue({
      id: "delivery-id",
      webhook_id: "webhook-id",
      webhook_name: "Outbound CRM",
      event: "lead.created",
      status: "retrying",
      attempt_count: 2,
      max_attempts: 5,
      next_attempt_at: "2026-07-22T10:10:00Z",
      response_code: 503,
      error_code: "HTTP_503",
      duration_ms: 1400,
      job_id: "delivery-job",
      correlation_id: "corr-retry",
      delivered_at: null,
      created_at: "2026-07-22T10:00:00Z",
      updated_at: "2026-07-22T10:05:00Z",
      payload: { lead: "redacted" },
      payload_hash: "hash",
      idempotency_key: "idem",
      error_message: "provider unavailable",
      transition_history: [
        {
          transition: "retry",
          from_status: "delivering",
          to_status: "retrying",
          occurred_at: "2026-07-22T10:05:00Z",
          transition_key: "retry-transition",
        },
      ],
      attempts: [
        {
          id: "attempt-id",
          attempt_number: 2,
          outcome: "retrying",
          response_code: 503,
          error_code: "HTTP_503",
          duration_ms: 1400,
          job_id: "delivery-job",
          correlation_id: "corr-retry",
          occurred_at: "2026-07-22T10:05:00Z",
        },
      ],
    });

    renderWithRoute(
      <DeliveryDetailPage />,
      "/integration-platform/deliveries/delivery-id",
      "/integration-platform/deliveries/:id"
    );

    expect(await screen.findByText("provider unavailable")).toBeInTheDocument();
    expect(screen.getByText("HTTP_503")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Redrive" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Redrive" }));
    expect(calls.redriveDelivery).not.toHaveBeenCalled();
  });

  it("leaves failed redrive attempts observable without fabricating success evidence", async () => {
    calls.getDelivery.mockResolvedValue({
      id: "delivery-id",
      webhook_id: "webhook-id",
      webhook_name: "Outbound CRM",
      event: "lead.created",
      status: "dead_letter",
      attempt_count: 5,
      max_attempts: 5,
      next_attempt_at: null,
      response_code: null,
      error_code: "HTTP_503",
      duration_ms: null,
      job_id: "delivery-job",
      correlation_id: "corr-dead",
      delivered_at: null,
      created_at: "2026-07-22T10:00:00Z",
      updated_at: "2026-07-22T10:05:00Z",
      payload: { lead: "redacted" },
      payload_hash: "hash",
      idempotency_key: "idem",
      error_message: "provider unavailable",
      transition_history: [],
      attempts: [],
    });
    calls.redriveDelivery.mockRejectedValue(new Error("redrive rejected by policy"));

    renderWithRoute(
      <DeliveryDetailPage />,
      "/integration-platform/deliveries/delivery-id",
      "/integration-platform/deliveries/:id"
    );
    await userEvent.click(await screen.findByRole("button", { name: "Redrive" }));

    await waitFor(() =>
      expect(calls.redriveDelivery).toHaveBeenCalledWith("delivery-id", {
        transition_key: "redrive-operation-id",
      })
    );
    expect(screen.queryByText("Redrive accepted")).not.toBeInTheDocument();
  });

  it("previews, applies, exports, and rolls back configuration with explicit evidence", async () => {
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:config"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    const objectUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:config");
    const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    calls.listConfigurationVersions.mockResolvedValue({
      items: [
        {
          id: "version-1",
          environment: "development",
          version: 1,
          document: configDocument,
          created_by: "operator",
          correlation_id: "corr-v1",
          created_at: "2026-07-21T00:00:00Z",
        },
      ],
      meta: { ...meta, count: 1 },
    });
    calls.listConfigurationAudits.mockResolvedValue({
      items: [
        {
          id: "audit-1",
          environment: "development",
          action: "update",
          from_version: 1,
          to_version: 2,
          before: configDocument,
          after: configDocument,
          changed_by: "operator",
          correlation_id: "corr-audit",
          created_at: "2026-07-22T00:00:00Z",
        },
      ],
      meta: { ...meta, count: 1 },
    });
    calls.previewConfiguration.mockResolvedValue({
      valid: true,
      environment: "staging",
      from_version: 2,
      to_version: 3,
      changed_sections: ["environment"],
      before: configDocument,
      after: { ...configDocument, environment: "staging" },
    });
    calls.saveConfiguration.mockResolvedValue({ ...configuration, version: 3 });
    calls.rollbackConfiguration.mockResolvedValue({ ...configuration, version: 4 });
    calls.importConfiguration.mockResolvedValue({ ...configuration, version: 5 });
    calls.exportConfiguration.mockResolvedValue({ ...configuration, environment: "development" });
    renderWithRoute(<ConfigurationPage />, "/integration-platform/configuration");
    await userEvent.clear(await screen.findByLabelText("Environment"));
    await userEvent.type(screen.getByLabelText("Environment"), "staging");
    await userEvent.click(screen.getByRole("button", { name: /Preview & apply/iu }));
    expect(await screen.findByText(/Previewed changes: environment/iu)).toBeInTheDocument();
    expect(calls.saveConfiguration).toHaveBeenCalledWith(
      expect.objectContaining({ environment: "staging" })
    );

    await userEvent.click(screen.getByRole("button", { name: /Export/iu }));
    expect(objectUrl).toHaveBeenCalled();
    expect(revoke).toHaveBeenCalledWith("blob:config");
    await userEvent.click(screen.getByRole("button", { name: /Rollback/iu }));
    expect(calls.rollbackConfiguration).toHaveBeenCalledWith("staging", 1);
  });

  it("fails closed for malformed configuration imports before server mutation", async () => {
    const rendered = renderWithRoute(<ConfigurationPage />, "/integration-platform/configuration");
    await screen.findByRole("heading", { name: "Integration Platform configuration" });

    const input = rendered.container.querySelector('input[type="file"]');
    if (!(input instanceof HTMLInputElement))
      throw new Error("Configuration import input missing.");
    const file = new File([JSON.stringify({ environment: "development" })], "invalid.json", {
      type: "application/json",
    });
    const readText = vi.fn().mockResolvedValue(JSON.stringify({ environment: "development" }));
    Object.defineProperty(file, "text", {
      configurable: true,
      value: readText,
    });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(readText).toHaveBeenCalled());
    expect(calls.previewConfiguration).not.toHaveBeenCalled();
    expect(calls.importConfiguration).not.toHaveBeenCalled();
    expect(calls.saveConfiguration).not.toHaveBeenCalled();
  });

  it("creates credentials through schema validation without exposing submitted secret values", async () => {
    calls.createCredential.mockResolvedValue({
      id: "cred-id",
      integration_id: "integration-id",
      credential_type: "certificate",
      display_hint: "cert",
      version: 1,
      status: "active",
      expires_at: null,
      rotated_at: null,
      revoked_at: null,
      created_at: "2026-07-22T00:00:00Z",
    });
    renderWithRoute(
      <CreateCredentialPage />,
      "/integration-platform/int-id/credentials/new",
      "/integration-platform/:id/credentials/new"
    );
    await userEvent.selectOptions(await screen.findByLabelText("Credential type"), "certificate");
    await userEvent.type(screen.getByLabelText("New credential value"), "pem-value");
    await userEvent.click(screen.getByRole("button", { name: "Create credential" }));
    await waitFor(() =>
      expect(calls.createCredential).toHaveBeenCalledWith("int-id", {
        credential_type: "certificate",
        plaintext: "pem-value",
        expires_at: null,
      })
    );
  });

  it("updates integration configuration with exact non-secret payloads and guarded cancellation", async () => {
    calls.getIntegration.mockResolvedValue({
      id: "33333333-3333-4333-8333-333333333333",
      connector_id: connector.id,
      connector_name: connector.name,
      name: "Warehouse sync",
      description: "Nightly pull",
      integration_type: "api",
      status: "inactive",
      last_tested_at: null,
      last_test_job_id: null,
      last_sync_job_id: null,
      last_error_code: "",
      last_error_message: "",
      credentials_count: 0,
      mappings_count: 0,
      created_at: "2026-07-22T00:00:00Z",
      updated_at: "2026-07-22T00:00:00Z",
      config: { base_url: "https://crm.example.test", sandbox: false },
      transition_history: [],
      latest_test_evidence: null,
      latest_sync_evidence: null,
    });
    calls.getConnectorSchema.mockResolvedValue(schema);
    calls.updateIntegration.mockResolvedValue({});
    vi.mocked(window.confirm).mockReturnValueOnce(false).mockReturnValueOnce(true);

    renderWithRoute(
      <EditIntegrationPage />,
      "/integration-platform/33333333-3333-4333-8333-333333333333/edit",
      "/integration-platform/:id/edit"
    );

    const name = await screen.findByLabelText("Name");
    await userEvent.clear(name);
    await userEvent.type(name, "Warehouse sync v2");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText("navigated")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(calls.updateIntegration).toHaveBeenCalledWith("33333333-3333-4333-8333-333333333333", {
        name: "Warehouse sync v2",
        description: "Nightly pull",
        config: { base_url: "https://crm.example.test", sandbox: false },
      })
    );
  });

  it("revokes credential metadata and rotates write-only credentials with idempotency", async () => {
    const activeCredential = {
      id: "cred-id",
      integration_id: "int-id",
      credential_type: "api_key",
      display_hint: "last4",
      version: 2,
      status: "active",
      expires_at: null,
      rotated_at: null,
      revoked_at: null,
      created_at: "2026-07-22T00:00:00Z",
    };
    calls.listCredentials.mockResolvedValue([activeCredential]);
    calls.revokeCredential.mockResolvedValue({ ...activeCredential, status: "revoked" });
    const metadataPage = renderWithRoute(
      <CredentialMetadataPage />,
      "/integration-platform/int-id/credentials",
      "/integration-platform/:id/credentials"
    );

    expect(await screen.findByText("last4")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Revoke" }));
    await waitFor(() =>
      expect(calls.revokeCredential).toHaveBeenCalledWith("cred-id", {
        transition_key: "revoke-operation-id",
      })
    );
    metadataPage.unmount();

    calls.getCredential.mockResolvedValue(activeCredential);
    calls.rotateCredential.mockResolvedValue({ ...activeCredential, version: 3 });
    renderWithRoute(
      <RotateCredentialPage />,
      "/integration-platform/int-id/credentials/cred-id/rotate",
      "/integration-platform/:id/credentials/:credentialId/rotate"
    );

    expect(await screen.findByRole("heading", { name: "Rotate credential" })).toBeInTheDocument();
    expect(screen.getByLabelText("Credential type")).toBeDisabled();
    await userEvent.type(screen.getByLabelText("New credential value"), "rotated-secret");
    await userEvent.click(screen.getByRole("button", { name: "Rotate credential" }));
    await waitFor(() =>
      expect(calls.rotateCredential).toHaveBeenCalledWith("cred-id", {
        plaintext: "rotated-secret",
        expires_at: null,
        idempotency_key: "rotate-operation-id",
      })
    );
  });

  it("renders populated integration rows, connector filters, pagination, and removable filters", async () => {
    calls.listConnectors.mockReset();
    calls.listIntegrations.mockReset();
    calls.listConnectors.mockResolvedValue({ items: [connector], meta: { ...meta, count: 1 } });
    calls.listIntegrations.mockResolvedValue({
      items: [
        {
          id: "33333333-3333-4333-8333-333333333333",
          connector_id: connector.id,
          connector_name: "CRM connector",
          name: "Warehouse sync",
          description: "Nightly pull",
          integration_type: "message_queue",
          status: "active",
          last_tested_at: "2026-07-22T00:00:00Z",
          last_test_job_id: "test-job-abcdef",
          last_sync_job_id: "sync-job-abcdef",
          last_error_code: "",
          last_error_message: "",
          credentials_count: 1,
          mappings_count: 2,
          created_at: "2026-07-22T00:00:00Z",
          updated_at: "2026-07-23T00:00:00Z",
          config: { base_url: "https://crm.example.test" },
          transition_history: [],
          latest_test_evidence: null,
          latest_sync_evidence: null,
        },
      ],
      meta: { ...meta, count: 1, total_pages: 2, has_next: true },
    });

    renderPage(`/integration-platform?connector=${connector.id}&status=active&type=api`);

    expect(await screen.findByRole("link", { name: "Warehouse sync" })).toBeInTheDocument();
    expect(screen.getByText(/message queue/iu)).toBeInTheDocument();
    expect(screen.getByText("test-job")).toBeInTheDocument();
    expect(screen.getByText("sync-job")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Filter by connector"), "");
    await waitFor(() =>
      expect(calls.listIntegrations).toHaveBeenLastCalledWith(
        expect.not.objectContaining({ connector_id: connector.id })
      )
    );
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() =>
      expect(calls.listIntegrations).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }))
    );
  });

  it("surfaces connector catalog failures and setup mutation errors without side effects", async () => {
    calls.listConnectors.mockReset();
    calls.getConnectorSchema.mockReset();
    calls.createIntegration.mockReset();
    calls.listConnectors.mockRejectedValue(
      new ApiError("Connector registry unavailable", 503, undefined, "REGISTRY_DOWN", "corr-cat")
    );

    const failedCatalog = renderWithRoute(<CreateIntegrationPage />, "/integration-platform/new");

    expect(await screen.findByText("Connector registry unavailable")).toBeInTheDocument();
    expect(screen.getByText(/corr-cat/iu)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(calls.listConnectors).toHaveBeenCalledTimes(2));
    failedCatalog.unmount();

    calls.listConnectors.mockReset();
    calls.listConnectors.mockResolvedValue({ items: [connector], meta: { ...meta, count: 1 } });
    calls.getConnectorSchema.mockResolvedValue(schema);
    calls.createIntegration.mockRejectedValue(new Error("adapter policy rejected create"));

    renderWithRoute(<CreateIntegrationPage />, "/integration-platform/new");
    await userEvent.click(await screen.findByRole("button", { name: /CRM connector/iu }));
    await userEvent.type(await screen.findByLabelText(/Base URL/iu), "https://crm.example.test");
    await userEvent.type(screen.getByLabelText("Integration name"), "Warehouse sync");
    await userEvent.click(screen.getByRole("button", { name: "Create & test connection" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("adapter policy rejected create");
    expect(calls.createCredential).not.toHaveBeenCalled();
    expect(calls.testIntegration).not.toHaveBeenCalled();
  });

  it("renders unavailable connector reasons during guided setup", async () => {
    calls.listConnectors.mockReset();
    calls.listConnectors.mockResolvedValue({
      items: [
        { ...connector, id: "adapter-down", name: "Adapter down", adapter_available: false },
        {
          ...connector,
          id: "locked",
          name: "Locked connector",
          is_entitled: false,
          entitlement_reason: undefined,
          required_entitlement: "crm.integration",
        },
      ],
      meta: { ...meta, count: 2 },
    });

    renderWithRoute(<CreateIntegrationPage />, "/integration-platform/new");

    expect(await screen.findByRole("button", { name: /Adapter down/iu })).toBeDisabled();
    expect(screen.getByText("Adapter unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Locked connector/iu })).toBeDisabled();
    expect(screen.getByText("Locked: crm.integration")).toBeInTheDocument();
  });

  it("renders inactive integration evidence, activation, and audited delete confirmation", async () => {
    const inactiveIntegration = {
      id: "33333333-3333-4333-8333-333333333333",
      connector_id: connector.id,
      connector_name: connector.name,
      name: "Warehouse sync",
      description: "",
      integration_type: "api",
      status: "inactive",
      last_tested_at: null,
      last_test_job_id: null,
      last_sync_job_id: null,
      last_error_code: "AUTH_FAILED",
      last_error_message: "Credential was revoked upstream.",
      credentials_count: 1,
      mappings_count: 0,
      created_at: "2026-07-22T00:00:00Z",
      updated_at: "2026-07-22T00:00:00Z",
      config: { base_url: "https://crm.example.test" },
      transition_history: [],
      latest_test_evidence: {
        outcome: "failed",
        correlation_id: "corr-test-failed",
        duration_ms: null,
        checked_at: "2026-07-22T00:00:00Z",
      },
      latest_sync_evidence: {
        outcome: "succeeded",
        correlation_id: "corr-sync-ok",
        records_read: 2,
        records_written: null,
        duration_ms: 30,
        completed_at: "2026-07-22T00:00:00Z",
      },
    } as const;
    calls.getIntegration.mockResolvedValue(inactiveIntegration);
    calls.listCredentials.mockResolvedValue([
      {
        id: "cred-id",
        integration_id: inactiveIntegration.id,
        credential_type: "oauth_token",
        display_hint: "",
        version: 1,
        status: "active",
        expires_at: null,
        rotated_at: null,
        revoked_at: null,
        created_at: "2026-07-22T00:00:00Z",
      },
    ]);
    calls.listMappings.mockResolvedValue({ items: [], meta });
    calls.activateIntegration.mockResolvedValue({
      job_id: "activate-job",
      status: "queued",
      correlation_id: "corr-activate",
      accepted_at: "2026-07-22T00:00:00Z",
      poll_after_ms: 1000,
    });
    calls.deleteIntegration.mockResolvedValue(undefined);
    vi.mocked(window.prompt).mockReturnValue("Warehouse sync");

    renderWithRoute(
      <IntegrationDetailPage />,
      "/integration-platform/33333333-3333-4333-8333-333333333333",
      "/integration-platform/:id"
    );

    expect(await screen.findByText("CRM connector integration")).toBeInTheDocument();
    expect(screen.getByText("AUTH_FAILED: Credential was revoked upstream.")).toBeInTheDocument();
    expect(screen.getByText("oauth token · redacted")).toBeInTheDocument();
    expect(screen.getByText("No mappings configured.")).toBeInTheDocument();
    expect(screen.getByText("corr-test-failed")).toBeInTheDocument();
    expect(screen.getByText("corr-sync-ok")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Activate" }));
    await waitFor(() =>
      expect(calls.activateIntegration).toHaveBeenCalledWith(inactiveIntegration.id, {
        transition_key: "activate-operation-id",
      })
    );
    await userEvent.click(screen.getByRole("button", { name: /Delete/iu }));
    await waitFor(() =>
      expect(calls.deleteIntegration).toHaveBeenCalledWith(inactiveIntegration.id)
    );
    expect(await screen.findByText("navigated")).toBeInTheDocument();
  });

  it("blocks delete when workflow configuration denies the current integration status", async () => {
    calls.getIntegration.mockResolvedValue({
      id: "33333333-3333-4333-8333-333333333333",
      connector_id: connector.id,
      connector_name: connector.name,
      name: "Warehouse sync",
      description: "Active path",
      integration_type: "api",
      status: "active",
      last_tested_at: null,
      last_test_job_id: null,
      last_sync_job_id: null,
      last_error_code: "",
      last_error_message: "",
      credentials_count: 0,
      mappings_count: 0,
      created_at: "2026-07-22T00:00:00Z",
      updated_at: "2026-07-22T00:00:00Z",
      config: {},
      transition_history: [],
      latest_test_evidence: null,
      latest_sync_evidence: null,
    });
    calls.listCredentials.mockResolvedValue([]);
    calls.listMappings.mockResolvedValue({ items: [], meta });

    renderWithRoute(
      <IntegrationDetailPage />,
      "/integration-platform/33333333-3333-4333-8333-333333333333",
      "/integration-platform/:id"
    );

    expect(await screen.findByRole("button", { name: /Delete/iu })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: /Delete/iu }));
    expect(calls.deleteIntegration).not.toHaveBeenCalled();
  });

  it("renders credential empty and error states with retryable recovery", async () => {
    calls.listCredentials.mockReset();
    calls.listCredentials
      .mockRejectedValueOnce(new Error("credential metadata unavailable"))
      .mockResolvedValueOnce([]);

    renderWithRoute(
      <CredentialMetadataPage />,
      "/integration-platform/int-id/credentials",
      "/integration-platform/:id/credentials"
    );

    expect(await screen.findByText("credential metadata unavailable")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "credentials" })).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "Add credential" })[0]!);
    expect(await screen.findByText("navigated")).toBeInTheDocument();
  });

  it("renders rotate credential load failures and retries before accepting plaintext", async () => {
    const activeCredential = {
      id: "cred-id",
      integration_id: "int-id",
      credential_type: "api_key",
      display_hint: "last4",
      version: 2,
      status: "active",
      expires_at: null,
      rotated_at: null,
      revoked_at: null,
      created_at: "2026-07-22T00:00:00Z",
    };
    calls.getCredential
      .mockRejectedValueOnce(new Error("credential load failed"))
      .mockResolvedValueOnce(activeCredential);
    calls.rotateCredential.mockResolvedValue({ ...activeCredential, version: 3 });

    renderWithRoute(
      <RotateCredentialPage />,
      "/integration-platform/int-id/credentials/cred-id/rotate",
      "/integration-platform/:id/credentials/:credentialId/rotate"
    );

    expect(await screen.findByText("credential load failed")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Rotate credential" })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("New credential value"), "rotated-secret");
    await userEvent.click(screen.getByRole("button", { name: "Rotate credential" }));

    await waitFor(() =>
      expect(calls.rotateCredential).toHaveBeenCalledWith("cred-id", {
        plaintext: "rotated-secret",
        expires_at: null,
        idempotency_key: "rotate-operation-id",
      })
    );
  });
});
