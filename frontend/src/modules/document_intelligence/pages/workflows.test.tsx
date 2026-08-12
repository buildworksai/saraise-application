/* eslint-disable @typescript-eslint/no-unsafe-assignment -- reviewed existing generated/cohesive surface; zero-warning gate remains enforced for unsuppressed rules. */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ClassificationDetailPage } from "./ClassificationDetailPage";
import { ClassificationOverviewPage } from "./ClassificationOverviewPage";
import { ConfigurationPage } from "./ConfigurationPage";
import { CreateExtractionPage } from "./CreateExtractionPage";
import { CreateTemplatePage } from "./CreateTemplatePage";
import { CreateTrainingJobPage } from "./CreateTrainingJobPage";
import { EditTemplatePage } from "./EditTemplatePage";
import { ExtractionDetailPage } from "./ExtractionDetailPage";
import { TrainingJobDetailPage } from "./TrainingJobDetailPage";
import { TrainingModelPage } from "./TrainingModelPage";
import { TemplateDetailPage } from "./TemplateDetailPage";
import { TemplateListPage } from "./TemplateListPage";
import {
  DocumentIntelligenceApiError,
  documentIntelligenceService,
} from "../services/document-intelligence-service";
import { documentIntelligenceConfigurationKey } from "../hooks/use-document-intelligence-configuration";
import {
  candidateModel,
  classificationDetail,
  documentIntelligenceConfiguration,
  extractionDetail,
  jobSummary,
  modelDetail,
  page,
  retiredModel,
  templateDetail,
  timestamp,
  trainingDetail,
} from "./test-fixtures";

const authState = vi.hoisted(() => ({ user: null as { tenant_role: string | null } | null }));
vi.mock("@/stores/auth-store", () => ({
  useAuthStore: (selector: (state: typeof authState) => boolean) => selector(authState),
}));

function renderRoute(
  element: React.ReactElement,
  path = "/document-intelligence/test",
  pattern = path
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  client.setQueryData(documentIntelligenceConfigurationKey, documentIntelligenceConfiguration);
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={pattern} element={element} />
          <Route path="*" element={<p>Navigated</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function setAdmin(): void {
  authState.user = { tenant_role: "tenant_admin" };
}

// One suite preserves the end-to-end narrative across all document-intelligence operator workflows.
// eslint-disable-next-line max-lines-per-function
describe("document intelligence page workflows", () => {
  beforeEach(() => {
    vi.spyOn(documentIntelligenceService, "getConfiguration").mockResolvedValue(
      documentIntelligenceConfiguration
    );
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
    authState.user = null;
  });

  it("submits extraction references with a deterministic idempotency key and pending state", async () => {
    const create = vi
      .spyOn(documentIntelligenceService, "createExtraction")
      .mockImplementation(() => new Promise(() => undefined));
    renderRoute(<CreateExtractionPage />);

    fireEvent.change(screen.getByLabelText("DMS document UUID"), {
      target: { value: "document-1" },
    });
    fireEvent.change(screen.getByLabelText("Immutable version UUID"), {
      target: { value: "version-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Queue extraction" }));

    await waitFor(() =>
      expect(create).toHaveBeenCalledWith({
        document_id: "document-1",
        document_version_id: "version-1",
        engine: "tesseract",
        extraction_type: "text",
        template_id: undefined,
        idempotency_key: "document-intelligence:extract:document-1:version-1:text:tesseract",
      })
    );
    expect(screen.getByRole("button", { name: "Validating and queuing…" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Validating and queuing…" }).querySelector(".animate-spin")
    ).toBeInTheDocument();
  });

  it("keeps pristine and whitespace-only extraction forms non-submittable", () => {
    renderRoute(<CreateExtractionPage />);

    expect(screen.getByLabelText("DMS document UUID")).toHaveValue("");
    expect(screen.getByLabelText("Immutable version UUID")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Queue extraction" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Queue extraction" }).querySelector(".animate-spin")
    ).not.toBeInTheDocument();
    const pristineBeforeUnload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(pristineBeforeUnload);
    expect(pristineBeforeUnload.defaultPrevented).toBe(false);

    fireEvent.change(screen.getByLabelText("DMS document UUID"), {
      target: { value: "   " },
    });
    fireEvent.change(screen.getByLabelText("Immutable version UUID"), {
      target: { value: "   " },
    });
    expect(screen.getByRole("button", { name: "Queue extraction" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("DMS document UUID"), {
      target: { value: "document-1" },
    });
    fireEvent.change(screen.getByLabelText("Immutable version UUID"), {
      target: { value: "version-1" },
    });
    fireEvent.change(screen.getByLabelText("Extraction type"), { target: { value: "structured" } });
    fireEvent.change(screen.getByLabelText("Extraction template UUID"), {
      target: { value: "   " },
    });
    expect(screen.getByRole("button", { name: "Queue extraction" })).toBeDisabled();
  });

  it("trims structured extraction payloads, protects dirty forms, and navigates after success", async () => {
    const create = vi.spyOn(documentIntelligenceService, "createExtraction").mockResolvedValue({
      extraction: { ...extractionDetail, id: "extract-success" },
      job: jobSummary,
    });
    renderRoute(<CreateExtractionPage />);

    fireEvent.change(screen.getByLabelText("DMS document UUID"), {
      target: { value: "  DOCUMENT-1  " },
    });
    const beforeUnload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(beforeUnload);
    expect(beforeUnload.defaultPrevented).toBe(true);

    fireEvent.change(screen.getByLabelText("Immutable version UUID"), {
      target: { value: "  VERSION-1  " },
    });
    expect(screen.getByLabelText("Extraction type")).toHaveValue("text");
    expect(
      [...screen.getByLabelText("Extraction type").querySelectorAll("option")].map(
        (option) => option.value
      )
    ).toEqual(["text", "structured", "table", "zone"]);
    fireEvent.change(screen.getByLabelText("Extraction type"), { target: { value: "structured" } });
    expect(screen.getByLabelText("Extraction template UUID")).toBeRequired();
    expect(screen.getByRole("button", { name: "Queue extraction" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Engine"), { target: { value: "google_vision" } });
    expect(
      [...screen.getByLabelText("Engine").querySelectorAll("option")].map((option) => option.value)
    ).toEqual(["tesseract", "aws_textract", "azure_form_recognizer", "google_vision"]);
    fireEvent.change(screen.getByLabelText("Extraction template UUID"), {
      target: { value: "  TEMPLATE-1  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Queue extraction" }));

    await waitFor(() =>
      expect(create).toHaveBeenCalledWith({
        document_id: "DOCUMENT-1",
        document_version_id: "VERSION-1",
        engine: "google_vision",
        extraction_type: "structured",
        template_id: "TEMPLATE-1",
        idempotency_key: "document-intelligence:extract:document-1:version-1:structured:template-1",
      })
    );
    expect(await screen.findByText("Navigated")).toBeInTheDocument();
  });

  it("surfaces field errors, resets failed extraction mutations, and supports back navigation", async () => {
    vi.spyOn(documentIntelligenceService, "createExtraction").mockRejectedValue(
      new DocumentIntelligenceApiError("Validation failed", 400, "validation_error", "corr-400", {
        field_errors: [
          { field: "document_id", code: "invalid", message: "Document ID is invalid" },
          { field: "document_version_id", code: "invalid", message: "Version ID is invalid" },
          { field: "template_id", code: "required", message: "Template is required" },
        ],
      })
    );
    renderRoute(<CreateExtractionPage />);

    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(await screen.findByText("Navigated")).toBeInTheDocument();
    cleanup();
    renderRoute(<CreateExtractionPage />);

    fireEvent.change(screen.getByLabelText("DMS document UUID"), {
      target: { value: "document-1" },
    });
    fireEvent.change(screen.getByLabelText("Immutable version UUID"), {
      target: { value: "version-1" },
    });
    fireEvent.change(screen.getByLabelText("Extraction type"), { target: { value: "zone" } });
    fireEvent.change(screen.getByLabelText("Extraction template UUID"), {
      target: { value: "template-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Queue extraction" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Validation failed");
    expect(screen.getByText("Document ID is invalid")).toBeInTheDocument();
    expect(screen.getByText("Version ID is invalid")).toBeInTheDocument();
    expect(screen.getByText("Template is required")).toBeInTheDocument();
    expect(screen.getByLabelText("DMS document UUID")).toHaveAccessibleDescription(
      "Document ID is invalid"
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  });

  it("keeps extraction and configuration controls accessible to native validation", async () => {
    vi.spyOn(documentIntelligenceService, "listConfigurationVersions").mockResolvedValue([]);
    vi.spyOn(documentIntelligenceService, "listConfigurationAudit").mockResolvedValue([]);

    const extraction = renderRoute(<CreateExtractionPage />);
    const documentInput = await screen.findByLabelText("DMS document UUID");
    const extractionForm = documentInput.closest("form");
    expect(extractionForm).not.toHaveAttribute("novalidate");
    expect(screen.getByRole("combobox", { name: "Extraction type" })).toBe(
      screen.getByLabelText("Extraction type")
    );
    expect(screen.getByRole("combobox", { name: "Engine" })).toBe(screen.getByLabelText("Engine"));
    extraction.unmount();

    setAdmin();
    renderRoute(
      <ConfigurationPage />,
      "/document-intelligence/configuration",
      "/document-intelligence/configuration"
    );

    expect(
      await screen.findByRole("heading", { name: "Document intelligence configuration" })
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Automatically classify completed uploads")).toHaveAttribute(
      "type",
      "checkbox"
    );
  });

  it("requires configuration simulation before save and submits the normalized versioned payload", async () => {
    setAdmin();
    const normalized = {
      ...documentIntelligenceConfiguration.document,
      extraction: { ...documentIntelligenceConfiguration.document.extraction, max_active: 8 },
      feature_flags: {
        auto_classification_enabled: true,
        rollout_percentage: 25,
        allowed_roles: ["tenant_admin", "compliance_manager"],
        allowed_cohorts: ["pilot"],
      },
      ui: {
        ...documentIntelligenceConfiguration.document.ui,
        confidence_filter_presets: [0.4, 0.8, 0.95],
      },
    };
    vi.spyOn(documentIntelligenceService, "listConfigurationVersions").mockResolvedValue([]);
    vi.spyOn(documentIntelligenceService, "listConfigurationAudit").mockResolvedValue([]);
    const simulate = vi
      .spyOn(documentIntelligenceService, "simulateConfiguration")
      .mockResolvedValue({
        valid: true,
        normalized_document: normalized,
        changes: [
          { path: "extraction.max_active", before: 5, after: 8 },
          { path: "feature_flags.rollout_percentage", before: 0, after: 25 },
        ],
        requires_restart: false,
      });
    const update = vi.spyOn(documentIntelligenceService, "updateConfiguration").mockResolvedValue({
      ...documentIntelligenceConfiguration,
      version: 2,
      document: normalized,
    });

    renderRoute(
      <ConfigurationPage />,
      "/document-intelligence/configuration",
      "/document-intelligence/configuration"
    );

    expect(
      await screen.findByRole("heading", { name: "Document intelligence configuration" })
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save version" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Concurrent extractions"), { target: { value: "8" } });
    fireEvent.click(screen.getByLabelText("Automatically classify completed uploads"));
    fireEvent.change(screen.getByLabelText("Rollout percentage"), { target: { value: "25" } });
    fireEvent.change(screen.getByLabelText("Rollout roles (comma-separated)"), {
      target: { value: " tenant_admin, compliance_manager " },
    });
    fireEvent.change(screen.getByLabelText("Rollout cohorts (comma-separated)"), {
      target: { value: " pilot " },
    });
    fireEvent.change(screen.getByLabelText("Confidence filter presets (comma-separated)"), {
      target: { value: "0.4, 0.8, 0.95" },
    });
    fireEvent.change(screen.getByLabelText("Change reason"), {
      target: { value: "Pilot rollout validation" },
    });
    expect(screen.getByRole("button", { name: "Save version" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Preview changes" }));

    await waitFor(() =>
      expect(simulate).toHaveBeenCalledWith({
        environment: "development",
        document: expect.objectContaining({
          extraction: expect.objectContaining({ max_active: 8 }),
          feature_flags: expect.objectContaining({
            auto_classification_enabled: true,
            rollout_percentage: 25,
            allowed_roles: ["tenant_admin", "compliance_manager"],
            allowed_cohorts: ["pilot"],
          }),
          ui: expect.objectContaining({ confidence_filter_presets: [0.4, 0.8, 0.95] }),
        }),
      })
    );
    expect(await screen.findByText(/2 change\(s\) validated/u)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save version" }));

    await waitFor(() =>
      expect(update).toHaveBeenCalledWith({
        environment: "development",
        document: normalized,
        change_reason: "Pilot rollout validation",
      })
    );
  });

  it("fails closed for invalid configuration JSON and impossible editor zoom bounds", async () => {
    setAdmin();
    vi.spyOn(documentIntelligenceService, "listConfigurationVersions").mockResolvedValue([]);
    vi.spyOn(documentIntelligenceService, "listConfigurationAudit").mockResolvedValue([]);
    const simulate = vi.spyOn(documentIntelligenceService, "simulateConfiguration");
    const update = vi.spyOn(documentIntelligenceService, "updateConfiguration");

    renderRoute(
      <ConfigurationPage />,
      "/document-intelligence/configuration",
      "/document-intelligence/configuration"
    );

    expect(await screen.findByLabelText("Configuration JSON")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Configuration JSON"), { target: { value: "{" } });
    expect(
      screen.getByText(/Expected property name|Unexpected end of JSON input/u)
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Minimum editor zoom"), { target: { value: "200" } });
    fireEvent.change(screen.getByLabelText("Maximum editor zoom"), { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText("Change reason"), { target: { value: "Bad zoom" } });

    expect(
      screen.getByText("Minimum editor zoom cannot exceed maximum editor zoom.")
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save version" })).toBeDisabled();
    expect(simulate).not.toHaveBeenCalled();
    expect(update).not.toHaveBeenCalled();
  });

  // eslint-disable-next-line max-lines-per-function -- one scenario verifies export/import/rollback evidence stays coherent.
  it("exports, imports, rolls back, and renders immutable configuration audit evidence", async () => {
    setAdmin();
    const previousVersion = {
      id: "00000000-0000-4000-8000-000000000701",
      tenant_id: documentIntelligenceConfiguration.tenant_id,
      environment: "development" as const,
      version: 1,
      document: documentIntelligenceConfiguration.document,
      created_by: documentIntelligenceConfiguration.created_by,
      created_at: timestamp,
      correlation_id: "corr-version-1",
      change_reason: "Initial policy",
    };
    const retainedVersion = { ...previousVersion, id: "version-retained", version: 3 };
    const currentVersion = { ...previousVersion, id: "version-current", version: 1 };
    vi.spyOn(documentIntelligenceService, "listConfigurationVersions").mockResolvedValue([
      currentVersion,
      retainedVersion,
    ]);
    vi.spyOn(documentIntelligenceService, "listConfigurationAudit").mockResolvedValue([
      {
        id: "audit-1",
        tenant_id: documentIntelligenceConfiguration.tenant_id,
        environment: "development",
        version: 1,
        operation: "rollback",
        previous_document: documentIntelligenceConfiguration.document,
        new_document: documentIntelligenceConfiguration.document,
        created_by: "operator-1",
        created_at: timestamp,
        correlation_id: "corr-audit-rollback",
        change_reason: "Rollback to approved policy",
      },
    ]);
    const exportConfiguration = vi
      .spyOn(documentIntelligenceService, "exportConfiguration")
      .mockResolvedValue({
        schema_version: 1,
        module: "document_intelligence",
        environment: "development",
        version: 1,
        exported_at: timestamp,
        document: documentIntelligenceConfiguration.document,
      });
    const importConfiguration = vi
      .spyOn(documentIntelligenceService, "importConfiguration")
      .mockResolvedValue(documentIntelligenceConfiguration);
    const rollbackConfiguration = vi
      .spyOn(documentIntelligenceService, "rollbackConfiguration")
      .mockResolvedValue(documentIntelligenceConfiguration);
    const click = vi.fn();
    const createObjectURL = vi.fn(() => "blob:document-intelligence");
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectURL, configurable: true });
    const originalCreateElement = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tagName) => {
      const element = originalCreateElement(tagName);
      if (tagName === "a") Object.assign(element, { click });
      return element;
    });

    renderRoute(
      <ConfigurationPage />,
      "/document-intelligence/configuration",
      "/document-intelligence/configuration"
    );

    expect(
      await screen.findByRole("heading", { name: "Document intelligence configuration" })
    ).toBeInTheDocument();
    expect(screen.getByText("corr-audit-rollback")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Export" }));
    await waitFor(() => expect(exportConfiguration).toHaveBeenCalledOnce());
    expect(createObjectURL).toHaveBeenCalled();
    expect(click).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:document-intelligence");

    fireEvent.change(screen.getByLabelText("Exported JSON document"), {
      target: {
        value: JSON.stringify({
          schema_version: 1,
          module: "document_intelligence",
          environment: "development",
          version: 1,
          exported_at: timestamp,
          document: documentIntelligenceConfiguration.document,
        }),
      },
    });
    expect(screen.getByRole("button", { name: "Validate and import" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Change reason"), {
      target: { value: "Promote reviewed configuration" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Validate and import" }));
    await waitFor(() =>
      expect(importConfiguration).toHaveBeenCalledWith({
        schema_version: 1,
        module: "document_intelligence",
        environment: "development",
        version: 1,
        exported_at: timestamp,
        document: documentIntelligenceConfiguration.document,
        change_reason: "Promote reviewed configuration",
      })
    );

    const rollbackButtons = screen.getAllByRole("button", { name: "Rollback" });
    expect(rollbackButtons[0]).toBeDisabled();
    fireEvent.click(rollbackButtons[1]!);
    await waitFor(() =>
      expect(rollbackConfiguration).toHaveBeenCalledWith({
        version: 3,
        environment: "development",
        change_reason: "Promote reviewed configuration",
      })
    );
  });

  it("rejects malformed document-intelligence configuration imports before the service call", async () => {
    setAdmin();
    vi.spyOn(documentIntelligenceService, "listConfigurationVersions").mockResolvedValue([]);
    vi.spyOn(documentIntelligenceService, "listConfigurationAudit").mockResolvedValue([]);
    const importConfiguration = vi.spyOn(documentIntelligenceService, "importConfiguration");

    renderRoute(
      <ConfigurationPage />,
      "/document-intelligence/configuration",
      "/document-intelligence/configuration"
    );

    expect(await screen.findByLabelText("Exported JSON document")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Change reason"), {
      target: { value: "Reject malformed import" },
    });
    fireEvent.change(screen.getByLabelText("Exported JSON document"), { target: { value: "[]" } });
    fireEvent.click(screen.getByRole("button", { name: "Validate and import" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Document intelligence unavailable");
    expect(importConfiguration).not.toHaveBeenCalled();
  });

  it("renders immutable extraction evidence and the explicit page-empty state", async () => {
    vi.spyOn(documentIntelligenceService, "getExtraction").mockResolvedValue(extractionDetail);
    vi.spyOn(documentIntelligenceService, "listExtractionPages").mockResolvedValue(page([]));
    renderRoute(
      <ExtractionDetailPage />,
      `/document-intelligence/extractions/${extractionDetail.id}`,
      "/document-intelligence/extractions/:id"
    );

    expect(await screen.findByText("Immutable DMS source")).toBeInTheDocument();
    expect(screen.getByText("Page evidence is not available yet.")).toBeInTheDocument();
    expect(screen.getByText(extractionDetail.document_version_id)).toBeInTheDocument();
  });

  // eslint-disable-next-line max-lines-per-function -- one scenario preserves extraction evidence tabs with both governed actions.
  it("renders extraction result tabs and guards retry and cancel command payloads", async () => {
    setAdmin();
    const failedExtraction = {
      ...extractionDetail,
      status: "failed" as const,
      confidence: null,
      processing_time_ms: null,
      failure_code: "provider_timeout",
      failure_message: "OCR provider timed out",
    };
    vi.spyOn(documentIntelligenceService, "getExtraction").mockResolvedValue(failedExtraction);
    vi.spyOn(documentIntelligenceService, "listExtractionPages").mockResolvedValue(
      page([
        {
          id: "00000000-0000-4000-8000-000000000110",
          tenant_id: extractionDetail.tenant_id,
          created_by: extractionDetail.created_by,
          extraction: extractionDetail.id,
          page_number: 1,
          width: 800,
          height: 1000,
          raw_text: "Total due 125.00",
          structured_data: {
            schema_version: "1.0",
            fields: [
              {
                key: "total",
                raw_value: "125.00",
                normalized_value: "125.00",
                data_type: "decimal",
                confidence: "0.9100",
                page_number: 1,
                bounds: null,
                source_span: { start: 10, end: 16 },
                validation: [{ rule: "required", valid: true, message: "present" }],
              },
            ],
          },
          table_data: [
            {
              page_number: 1,
              rows: 1,
              columns: 1,
              bounds: null,
              cells: [
                {
                  row: 1,
                  column: 1,
                  row_span: 1,
                  column_span: 1,
                  value: "125.00",
                  confidence: "0.9000",
                  bounds: null,
                },
              ],
            },
          ],
          confidence: "0.9100",
          provider_metadata: {
            adapter_key: "tesseract",
            adapter_version: "5",
            provider_request_id: "request-1",
            result_checksum: "sha256:page",
          },
          created_at: timestamp,
          updated_at: timestamp,
        },
      ])
    );
    const retry = vi
      .spyOn(documentIntelligenceService, "retryExtraction")
      .mockResolvedValue({ extraction: failedExtraction, job: jobSummary });
    renderRoute(
      <ExtractionDetailPage />,
      `/document-intelligence/extractions/${failedExtraction.id}`,
      "/document-intelligence/extractions/:id"
    );

    expect(await screen.findByText("Total due 125.00")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "structured" }));
    expect(screen.getByText("total")).toBeInTheDocument();
    expect(screen.getByText("125.00")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "table" }));
    expect(screen.getByText("Table 1 · 1 × 1")).toBeInTheDocument();
    expect(screen.getByText("provider_timeout: OCR provider timed out")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Queue retry" })
    );

    await waitFor(() =>
      expect(retry).toHaveBeenCalledWith(failedExtraction.id, {
        idempotency_key: `document-intelligence:retry-extraction:${failedExtraction.id}:${failedExtraction.async_job_id}`,
      })
    );

    cleanup();
    const queuedExtraction = { ...extractionDetail, status: "processing" as const };
    vi.spyOn(documentIntelligenceService, "getExtraction").mockResolvedValue(queuedExtraction);
    vi.spyOn(documentIntelligenceService, "listExtractionPages").mockResolvedValue(page([]));
    const cancel = vi
      .spyOn(documentIntelligenceService, "cancelExtraction")
      .mockResolvedValue({ ...queuedExtraction, status: "cancelled" });
    renderRoute(
      <ExtractionDetailPage />,
      `/document-intelligence/extractions/${queuedExtraction.id}`,
      "/document-intelligence/extractions/:id"
    );

    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel extraction" })
    );
    await waitFor(() =>
      expect(cancel).toHaveBeenCalledWith(queuedExtraction.id, {
        reason: "Cancelled by operator",
      })
    );
  });

  it("fails closed when extraction evidence or page evidence cannot be loaded", async () => {
    vi.spyOn(documentIntelligenceService, "getExtraction").mockRejectedValue(
      new DocumentIntelligenceApiError(
        "Extraction hidden",
        404,
        "not_found",
        "corr-extract-404",
        {}
      )
    );
    const listPages = vi.spyOn(documentIntelligenceService, "listExtractionPages");
    renderRoute(
      <ExtractionDetailPage />,
      `/document-intelligence/extractions/${extractionDetail.id}`,
      "/document-intelligence/extractions/:id"
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Access unavailable");
    expect(screen.getByText("Correlation ID: corr-extract-404")).toBeInTheDocument();
    expect(listPages).toHaveBeenCalledWith(extractionDetail.id);

    cleanup();
    vi.spyOn(documentIntelligenceService, "getExtraction").mockResolvedValue(extractionDetail);
    vi.spyOn(documentIntelligenceService, "listExtractionPages").mockRejectedValue(
      new DocumentIntelligenceApiError(
        "Provider evidence unavailable",
        503,
        "provider_down",
        "corr-pages",
        {}
      )
    );
    renderRoute(
      <ExtractionDetailPage />,
      `/document-intelligence/extractions/${extractionDetail.id}`,
      "/document-intelligence/extractions/:id"
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Provider evidence unavailable");
    expect(screen.getByText("Correlation ID: corr-pages")).toBeInTheDocument();
  });

  it("records review separately from the immutable classification result", async () => {
    setAdmin();
    vi.spyOn(documentIntelligenceService, "getClassification").mockResolvedValue(
      classificationDetail
    );
    vi.spyOn(documentIntelligenceService, "listClassificationScores").mockResolvedValue(page([]));
    const review = vi.spyOn(documentIntelligenceService, "reviewClassification").mockResolvedValue({
      ...classificationDetail,
      review_status: "corrected",
      reviewed_category: "purchase_order",
    });
    renderRoute(
      <ClassificationDetailPage />,
      `/document-intelligence/classifications/${classificationDetail.id}`,
      "/document-intelligence/classifications/:id"
    );

    fireEvent.click(await screen.findByRole("button", { name: "Review" }));
    fireEvent.change(screen.getByLabelText("Reviewed category slug"), {
      target: { value: "purchase_order" },
    });
    fireEvent.change(screen.getByLabelText("Review note"), {
      target: { value: "Verified against source" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save review" }));

    await waitFor(() =>
      expect(review).toHaveBeenCalledWith(classificationDetail.id, {
        category: "purchase_order",
        note: "Verified against source",
      })
    );
    expect(screen.getByText("invoice")).toBeInTheDocument();
  });

  it("guards classification retry, cancel, score-error reset, and review fallback payloads", async () => {
    setAdmin();
    const failedClassification = {
      ...classificationDetail,
      status: "timed_out" as const,
      category: null,
      confidence: null,
      secondary_category: "",
      secondary_confidence: null,
      failure_code: "classifier_timeout",
      failure_message: "Classifier timed out",
    };
    vi.spyOn(documentIntelligenceService, "getClassification").mockResolvedValue(
      failedClassification
    );
    vi.spyOn(documentIntelligenceService, "listClassificationScores").mockRejectedValue(
      new DocumentIntelligenceApiError("Scores sealed", 403, "forbidden", "corr-score", {})
    );
    const retry = vi
      .spyOn(documentIntelligenceService, "retryClassification")
      .mockResolvedValue({ classification: failedClassification, job: jobSummary });
    renderRoute(
      <ClassificationDetailPage />,
      `/document-intelligence/classifications/${failedClassification.id}`,
      "/document-intelligence/classifications/:id"
    );

    expect(await screen.findByText("Awaiting inference")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Access unavailable");
    fireEvent.click(screen.getAllByRole("button", { name: "Retry" })[0]!);
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Queue retry" })
    );
    await waitFor(() =>
      expect(retry).toHaveBeenCalledWith(failedClassification.id, {
        idempotency_key: `document-intelligence:retry-classification:${failedClassification.id}:${failedClassification.async_job_id}`,
      })
    );

    cleanup();
    const activeClassification = { ...classificationDetail, status: "queued" as const };
    vi.spyOn(documentIntelligenceService, "getClassification").mockResolvedValue(
      activeClassification
    );
    vi.spyOn(documentIntelligenceService, "listClassificationScores").mockResolvedValue(page([]));
    const cancel = vi
      .spyOn(documentIntelligenceService, "cancelClassification")
      .mockResolvedValue({ ...activeClassification, status: "cancelled" });
    renderRoute(
      <ClassificationDetailPage />,
      `/document-intelligence/classifications/${activeClassification.id}`,
      "/document-intelligence/classifications/:id"
    );

    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel job" }));
    await waitFor(() =>
      expect(cancel).toHaveBeenCalledWith(activeClassification.id, {
        reason: "Cancelled by operator",
      })
    );

    cleanup();
    vi.spyOn(documentIntelligenceService, "getClassification").mockResolvedValue(
      classificationDetail
    );
    vi.spyOn(documentIntelligenceService, "listClassificationScores").mockResolvedValue(
      page([
        {
          id: "00000000-0000-4000-8000-000000000120",
          tenant_id: classificationDetail.tenant_id,
          created_by: classificationDetail.created_by,
          classification: classificationDetail.id,
          category: "invoice",
          confidence: "0.8800",
          rank: 1,
          created_at: timestamp,
          updated_at: timestamp,
        },
      ])
    );
    const review = vi.spyOn(documentIntelligenceService, "reviewClassification").mockResolvedValue({
      ...classificationDetail,
      review_status: "confirmed",
      reviewed_category: "invoice",
    });
    renderRoute(
      <ClassificationDetailPage />,
      `/document-intelligence/classifications/${classificationDetail.id}`,
      "/document-intelligence/classifications/:id"
    );

    expect(await screen.findByText("#1 invoice")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Review" }));
    fireEvent.change(screen.getByLabelText("Reviewed category slug"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save review" }));
    await waitFor(() =>
      expect(review).toHaveBeenCalledWith(classificationDetail.id, {
        category: "invoice",
        note: "",
      })
    );
  });

  it("shows the classification empty state without exposing privileged actions", async () => {
    vi.spyOn(documentIntelligenceService, "listClassifications").mockResolvedValue(page([]));
    renderRoute(
      <ClassificationOverviewPage />,
      "/document-intelligence/classifications",
      "/document-intelligence/classifications"
    );

    expect(await screen.findByText("No classifications found")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Classify document" })).not.toBeInTheDocument();
  });

  it("applies classification filters, routes rows by keyboard, and queues a trimmed classification", async () => {
    setAdmin();
    const processing = { ...classificationDetail, status: "processing" as const };
    vi.spyOn(documentIntelligenceService, "listClassifications").mockResolvedValue(
      page([processing])
    );
    const create = vi.spyOn(documentIntelligenceService, "createClassification").mockResolvedValue({
      classification: { ...classificationDetail, id: "00000000-0000-4000-8000-000000000121" },
      job: jobSummary,
    });
    renderRoute(
      <ClassificationOverviewPage />,
      "/document-intelligence/classifications?status=processing&category=invoice&review=true",
      "/document-intelligence/classifications"
    );

    await waitFor(() =>
      expect(documentIntelligenceService.listClassifications).toHaveBeenCalledWith({
        page: 1,
        page_size: documentIntelligenceConfiguration.document.ui.page_size,
        status: "processing",
        category: "invoice",
        needs_review: true,
        ordering: "-created_at",
      })
    );
    expect(screen.getByText(/Auto-refreshing active work/u)).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("row", { name: /invoice/u }), { key: "Enter" });
    expect(await screen.findByText("Navigated")).toBeInTheDocument();

    cleanup();
    vi.spyOn(documentIntelligenceService, "listClassifications").mockResolvedValue(page([]));
    renderRoute(
      <ClassificationOverviewPage />,
      "/document-intelligence/classifications",
      "/document-intelligence/classifications"
    );

    fireEvent.click(await screen.findByRole("button", { name: "Classify document" }));
    fireEvent.change(screen.getByLabelText("DMS document UUID"), {
      target: { value: "  document-new  " },
    });
    fireEvent.change(screen.getByLabelText("Immutable version UUID"), {
      target: { value: "  version-new  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Queue classification" }));
    await waitFor(() =>
      expect(create).toHaveBeenCalledWith({
        document_id: "document-new",
        document_version_id: "version-new",
        idempotency_key: "document-intelligence:classify:document-new:version-new",
      })
    );
  });

  it("fails closed on classification overview service errors and supports explicit retry", async () => {
    const list = vi
      .spyOn(documentIntelligenceService, "listClassifications")
      .mockRejectedValueOnce(
        new DocumentIntelligenceApiError(
          "Classification query denied",
          403,
          "forbidden",
          "corr-class-list",
          {}
        )
      )
      .mockResolvedValueOnce(page([]));
    renderRoute(
      <ClassificationOverviewPage />,
      "/document-intelligence/classifications",
      "/document-intelligence/classifications"
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Access unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
  });

  it("creates a provider-neutral draft template from validated form state", async () => {
    const create = vi
      .spyOn(documentIntelligenceService, "createTemplate")
      .mockResolvedValue(templateDetail);
    renderRoute(<CreateTemplatePage />);

    fireEvent.change(await screen.findByLabelText("Template name"), {
      target: { value: "Invoice evidence" },
    });
    fireEvent.change(screen.getByLabelText("Document category (optional)"), {
      target: { value: "invoice" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create draft" }));

    await waitFor(() =>
      expect(create).toHaveBeenCalledWith({
        name: "Invoice evidence",
        description: "",
        document_category: "invoice",
        engine: "tesseract",
        match_threshold: "0.7000",
        zones: [],
      })
    );
  });

  it("protects active template evidence by offering a cloned draft instead of editing", async () => {
    const active = {
      ...templateDetail,
      status: "active" as const,
      activated_at: templateDetail.created_at,
    };
    vi.spyOn(documentIntelligenceService, "getTemplate").mockResolvedValue(active);
    vi.spyOn(documentIntelligenceService, "listTemplateZones").mockResolvedValue(page([]));
    const clone = vi.spyOn(documentIntelligenceService, "cloneTemplate").mockResolvedValue({
      ...templateDetail,
      id: "00000000-0000-4000-8000-000000000031",
      version: 2,
    });
    renderRoute(
      <EditTemplatePage />,
      `/document-intelligence/templates/${active.id}/edit`,
      "/document-intelligence/templates/:id/edit"
    );

    fireEvent.click(await screen.findByRole("button", { name: "Clone draft revision" }));
    await waitFor(() =>
      expect(clone).toHaveBeenCalledWith(active.id, { name: "Invoice template revision 2" })
    );
    expect(screen.queryByRole("button", { name: "Save template" })).not.toBeInTheDocument();
  });

  it("saves editable template revisions by updating, creating, and deleting normalized zones", async () => {
    const existingZone = {
      id: "00000000-0000-4000-8000-000000000130",
      tenant_id: templateDetail.tenant_id,
      created_by: templateDetail.created_by,
      template: templateDetail.id,
      zone_name: "Total",
      extraction_key: "total",
      zone_type: "text" as const,
      x: "0.1000",
      y: "0.1000",
      width: "0.3000",
      height: "0.1000",
      page_number: 1,
      expected_data_type: "decimal" as const,
      is_required: true,
      is_deleted: false,
      deleted_at: null,
      created_at: timestamp,
      updated_at: timestamp,
    };
    vi.spyOn(documentIntelligenceService, "getTemplate").mockResolvedValue(templateDetail);
    vi.spyOn(documentIntelligenceService, "listTemplateZones").mockResolvedValue(
      page([
        existingZone,
        {
          ...existingZone,
          id: "00000000-0000-4000-8000-000000000131",
          zone_name: "Obsolete",
          extraction_key: "obsolete",
        },
      ])
    );
    const updateTemplate = vi
      .spyOn(documentIntelligenceService, "updateTemplate")
      .mockResolvedValue(templateDetail);
    const updateZone = vi
      .spyOn(documentIntelligenceService, "updateTemplateZone")
      .mockResolvedValue(existingZone);
    const deleteZone = vi
      .spyOn(documentIntelligenceService, "deleteTemplateZone")
      .mockResolvedValue();
    renderRoute(
      <EditTemplatePage />,
      `/document-intelligence/templates/${templateDetail.id}/edit`,
      "/document-intelligence/templates/:id/edit"
    );

    fireEvent.change(await screen.findByLabelText("Template name"), {
      target: { value: "Invoice template governed" },
    });
    fireEvent.change(screen.getByLabelText("Match threshold"), { target: { value: "0.8500" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Remove" })[1]!);
    fireEvent.click(screen.getByRole("button", { name: "Save template" }));

    await waitFor(() =>
      expect(updateTemplate).toHaveBeenCalledWith(templateDetail.id, {
        name: "Invoice template governed",
        description: templateDetail.description,
        document_category: templateDetail.document_category,
        engine: templateDetail.engine,
        match_threshold: "0.8500",
      })
    );
    expect(updateZone).toHaveBeenCalledWith(
      existingZone.id,
      expect.objectContaining({ extraction_key: "total", is_required: true })
    );
    expect(deleteZone).toHaveBeenCalledWith("00000000-0000-4000-8000-000000000131");
    expect(await screen.findByText("Navigated")).toBeInTheDocument();
  });

  it("surfaces immutable edit-template clone failures without changing evidence", async () => {
    vi.spyOn(documentIntelligenceService, "getTemplate").mockResolvedValue({
      ...templateDetail,
      status: "retired",
    });
    vi.spyOn(documentIntelligenceService, "listTemplateZones").mockResolvedValue(page([]));
    vi.spyOn(documentIntelligenceService, "cloneTemplate").mockRejectedValue(
      new DocumentIntelligenceApiError("Clone denied", 403, "forbidden", "corr-clone", {})
    );
    renderRoute(
      <EditTemplatePage />,
      `/document-intelligence/templates/${templateDetail.id}/edit`,
      "/document-intelligence/templates/:id/edit"
    );

    fireEvent.click(await screen.findByRole("button", { name: "Clone draft revision" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Access unavailable");
    expect(screen.getByText("Correlation ID: corr-clone")).toBeInTheDocument();
  });

  it("renders template-list empty guidance and performs explicit draft activation", async () => {
    vi.spyOn(documentIntelligenceService, "listTemplates").mockResolvedValue(page([]));
    const listView = renderRoute(
      <TemplateListPage />,
      "/document-intelligence/templates",
      "/document-intelligence/templates"
    );
    expect(await screen.findByText("No extraction templates")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create template" })).not.toBeInTheDocument();
    listView.unmount();

    setAdmin();
    vi.spyOn(documentIntelligenceService, "getTemplate").mockResolvedValue(templateDetail);
    vi.spyOn(documentIntelligenceService, "listTemplateZones").mockResolvedValue(page([]));
    const activate = vi.spyOn(documentIntelligenceService, "activateTemplate").mockResolvedValue({
      ...templateDetail,
      status: "active",
      activated_at: templateDetail.created_at,
    });
    renderRoute(
      <TemplateDetailPage />,
      `/document-intelligence/templates/${templateDetail.id}`,
      "/document-intelligence/templates/:id"
    );

    fireEvent.click(await screen.findByRole("button", { name: "Activate" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Activate" }));
    // Vitest asymmetric matchers are intentionally untyped at this assertion boundary.
    // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
    await waitFor(() =>
      expect(activate).toHaveBeenCalledWith(
        templateDetail.id,
        expect.objectContaining({ transition_key: expect.any(String) })
      )
    );
  });

  it("filters and routes template list cards with admin create access", async () => {
    setAdmin();
    vi.spyOn(documentIntelligenceService, "listTemplates").mockResolvedValue(
      page([{ ...templateDetail, zone_count: 2 }])
    );
    renderRoute(
      <TemplateListPage />,
      "/document-intelligence/templates?status=active&category=invoice",
      "/document-intelligence/templates"
    );

    await waitFor(() =>
      expect(documentIntelligenceService.listTemplates).toHaveBeenCalledWith({
        page: 1,
        page_size: documentIntelligenceConfiguration.document.ui.page_size,
        status: "active",
        document_category: "invoice",
        ordering: "name",
      })
    );
    fireEvent.click(screen.getByRole("button", { name: "Open template" }));
    expect(await screen.findByText("Navigated")).toBeInTheDocument();

    cleanup();
    vi.spyOn(documentIntelligenceService, "listTemplates").mockResolvedValue(page([]));
    renderRoute(
      <TemplateListPage />,
      "/document-intelligence/templates",
      "/document-intelligence/templates"
    );

    fireEvent.click(await screen.findByRole("button", { name: "New template" }));
    expect(await screen.findByText("Navigated")).toBeInTheDocument();
  });

  it("executes active-template match, deactivate, and archive command boundaries", async () => {
    setAdmin();
    const activeTemplate = {
      ...templateDetail,
      status: "active" as const,
      activated_at: timestamp,
    };
    vi.spyOn(documentIntelligenceService, "getTemplate").mockResolvedValue(activeTemplate);
    vi.spyOn(documentIntelligenceService, "listTemplateZones").mockResolvedValue(page([]));
    const match = vi.spyOn(documentIntelligenceService, "matchTemplate").mockResolvedValue({
      matched: true,
      template_id: activeTemplate.id,
      confidence: "0.9200",
      processing_time_ms: 12,
      evidence: { threshold_met: true },
    });
    const deactivate = vi
      .spyOn(documentIntelligenceService, "deactivateTemplate")
      .mockResolvedValue({ ...activeTemplate, status: "inactive" });
    renderRoute(
      <TemplateDetailPage />,
      `/document-intelligence/templates/${activeTemplate.id}`,
      "/document-intelligence/templates/:id"
    );

    fireEvent.click(await screen.findByRole("button", { name: "Test match" }));
    fireEvent.change(screen.getByLabelText("DMS document UUID"), {
      target: { value: "document-match" },
    });
    fireEvent.change(screen.getByLabelText("Immutable version UUID"), {
      target: { value: "version-match" },
    });
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Run match" }));
    await waitFor(() =>
      expect(match).toHaveBeenCalledWith(activeTemplate.id, {
        document_id: "document-match",
        document_version_id: "version-match",
      })
    );

    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Deactivate" }));
    await waitFor(() =>
      expect(deactivate).toHaveBeenCalledWith(activeTemplate.id, {
        transition_key: expect.stringMatching(
          new RegExp(`^document-intelligence:deactivate:${activeTemplate.id}:`, "u")
        ),
      })
    );
    expect(screen.getByRole("button", { name: "Archive" })).toBeDisabled();

    cleanup();
    vi.spyOn(documentIntelligenceService, "getTemplate").mockResolvedValue(templateDetail);
    vi.spyOn(documentIntelligenceService, "listTemplateZones").mockResolvedValue(page([]));
    const archive = vi.spyOn(documentIntelligenceService, "archiveTemplate").mockResolvedValue();
    renderRoute(
      <TemplateDetailPage />,
      `/document-intelligence/templates/${templateDetail.id}`,
      "/document-intelligence/templates/:id"
    );

    fireEvent.click(await screen.findByRole("button", { name: "Archive" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Archive" }));
    await waitFor(() => expect(archive).toHaveBeenCalledWith(templateDetail.id));
    expect(await screen.findByText("Navigated")).toBeInTheDocument();
  });

  it("submits a real 50-item training set after client-side category validation", async () => {
    const create = vi
      .spyOn(documentIntelligenceService, "createTrainingJob")
      .mockImplementation(() => new Promise(() => undefined));
    const rows = Array.from(
      { length: 50 },
      (_, index) => `document-${index}, version-${index}, ${index < 25 ? "invoice" : "receipt"}`
    ).join("\n");
    renderRoute(<CreateTrainingJobPage />);

    fireEvent.change(await screen.findByLabelText("Training job name"), {
      target: { value: "AP classifier" },
    });
    fireEvent.change(screen.getByLabelText("Requested model version"), {
      target: { value: "2.0.0" },
    });
    fireEvent.change(screen.getByLabelText("Training examples"), { target: { value: rows } });
    fireEvent.click(screen.getByRole("button", { name: "Queue training" }));

    await waitFor(() => expect(create).toHaveBeenCalledOnce());
    const [request] = create.mock.calls[0]!;
    expect(request.items).toHaveLength(50);
    expect(request.idempotency_key).toMatch(/^document-intelligence:train:2.0.0:50:/u);
    expect(screen.getByRole("button", { name: "Validating and queuing…" })).toBeDisabled();
  });

  it("supports explicit candidate activation and retained-version rollback", async () => {
    setAdmin();
    vi.spyOn(documentIntelligenceService, "listTrainingJobs").mockResolvedValue(page([]));
    vi.spyOn(documentIntelligenceService, "listModelVersions").mockResolvedValue(
      page([candidateModel, retiredModel])
    );
    const activate = vi
      .spyOn(documentIntelligenceService, "activateModelVersion")
      .mockResolvedValue(modelDetail({ ...candidateModel, status: "active" }));
    const rollback = vi
      .spyOn(documentIntelligenceService, "rollbackModelVersion")
      .mockResolvedValue(modelDetail({ ...retiredModel, status: "active" }));
    renderRoute(
      <TrainingModelPage />,
      "/document-intelligence/training",
      "/document-intelligence/training"
    );

    fireEvent.click(await screen.findByRole("button", { name: "Activate candidate" }));
    fireEvent.click(screen.getByRole("button", { name: "Activate" }));
    // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
    await waitFor(() =>
      expect(activate).toHaveBeenCalledWith(
        candidateModel.id,
        expect.objectContaining({ transition_key: expect.any(String) })
      )
    );

    fireEvent.click(screen.getByRole("button", { name: "Rollback to version" }));
    fireEvent.click(screen.getByRole("button", { name: "Rollback" }));
    // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
    await waitFor(() =>
      expect(rollback).toHaveBeenCalledWith(
        retiredModel.id,
        expect.objectContaining({ transition_key: expect.any(String) })
      )
    );
  });

  it("renders training errors, empty-state actions, and job-row navigation", async () => {
    const jobs = vi
      .spyOn(documentIntelligenceService, "listTrainingJobs")
      .mockRejectedValueOnce(
        new DocumentIntelligenceApiError(
          "Training history unavailable",
          503,
          "unavailable",
          "corr-training",
          {}
        )
      )
      .mockResolvedValueOnce(page([]));
    vi.spyOn(documentIntelligenceService, "listModelVersions").mockResolvedValue(page([]));
    renderRoute(
      <TrainingModelPage />,
      "/document-intelligence/training",
      "/document-intelligence/training"
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Training history unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(jobs).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("No model versions")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start training" })).not.toBeInTheDocument();

    cleanup();
    setAdmin();
    vi.spyOn(documentIntelligenceService, "listTrainingJobs").mockResolvedValue(
      page([{ ...trainingDetail }])
    );
    vi.spyOn(documentIntelligenceService, "listModelVersions").mockResolvedValue(page([]));
    renderRoute(
      <TrainingModelPage />,
      "/document-intelligence/training?job_page=1&model_page=1",
      "/document-intelligence/training"
    );

    fireEvent.click(await screen.findByRole("button", { name: "Train model" }));
    expect(await screen.findByText("Navigated")).toBeInTheDocument();

    cleanup();
    setAdmin();
    vi.spyOn(documentIntelligenceService, "listTrainingJobs").mockResolvedValue(
      page([{ ...trainingDetail, status: "queued" }])
    );
    vi.spyOn(documentIntelligenceService, "listModelVersions").mockResolvedValue(page([]));
    renderRoute(
      <TrainingModelPage />,
      "/document-intelligence/training",
      "/document-intelligence/training"
    );

    expect(await screen.findByText(/Auto-refreshing active work/u)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("row", { name: /Invoice classifier/u }));
    expect(await screen.findByText("Navigated")).toBeInTheDocument();
  });

  it("keeps model transition failures visible until explicitly reset", async () => {
    setAdmin();
    vi.spyOn(documentIntelligenceService, "listTrainingJobs").mockResolvedValue(page([]));
    vi.spyOn(documentIntelligenceService, "listModelVersions").mockResolvedValue(
      page([candidateModel])
    );
    const activate = vi
      .spyOn(documentIntelligenceService, "activateModelVersion")
      .mockRejectedValueOnce(
        new DocumentIntelligenceApiError(
          "Accuracy below threshold",
          409,
          "not_ready",
          "corr-model",
          {}
        )
      );
    renderRoute(
      <TrainingModelPage />,
      "/document-intelligence/training",
      "/document-intelligence/training"
    );

    fireEvent.click(await screen.findByRole("button", { name: "Activate candidate" }));
    fireEvent.click(screen.getByRole("button", { name: "Activate" }));
    await waitFor(() =>
      expect(activate).toHaveBeenCalledWith(candidateModel.id, {
        transition_key: expect.stringMatching(
          new RegExp(`^document-intelligence:activate:${candidateModel.id}:`, "u")
        ),
      })
    );
    expect(
      await screen.findByText("The action failed. Review the page error and retry.")
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Keep unchanged" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Accuracy below threshold");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  });

  it("polls active training while preserving durable transition evidence", async () => {
    vi.useFakeTimers();
    const get = vi
      .spyOn(documentIntelligenceService, "getTrainingJob")
      .mockResolvedValue(trainingDetail);
    renderRoute(
      <TrainingJobDetailPage />,
      `/document-intelligence/training/${trainingDetail.id}`,
      "/document-intelligence/training/:id"
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText("Worker claimed job")).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    expect(get.mock.calls.length).toBeGreaterThan(1);
  });
});
