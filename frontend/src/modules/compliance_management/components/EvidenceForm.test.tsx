/* eslint-disable max-lines-per-function -- direct form mutation matrix keeps validation contracts in one file. */
import "@testing-library/jest-dom/vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { EvidenceWriteRequest } from "../contracts";
import { EvidenceForm } from "./EvidenceForm";

const baseEvidence: EvidenceWriteRequest = {
  name: "SOC report",
  description: "Annual control evidence",
  evidence_type: "report",
  reference_kind: "dms_document",
  classification: "internal",
  collection_method: "manual",
  document_id: "document-1",
  external_uri: "https://example.invalid/old.pdf",
  text_reference: "legacy note",
  sha256: "",
  collected_at: "2026-07-20T10:00:00.000Z",
  valid_from: "2026-07-01T00:00:00.000Z",
  valid_until: "2026-12-31T23:59:00.000Z",
};

function renderForm(props: Partial<Parameters<typeof EvidenceForm>[0]> = {}): ReturnType<
  typeof render
> & {
  onCancel: ReturnType<typeof vi.fn>;
  onSubmit: ReturnType<typeof vi.fn>;
} {
  const onSubmit = vi.fn();
  const onCancel = vi.fn();
  const view = render(
    <EvidenceForm
      pending={false}
      submitLabel="Save evidence"
      onSubmit={onSubmit}
      onCancel={onCancel}
      {...props}
    />
  );
  return { ...view, onCancel, onSubmit };
}

describe("EvidenceForm", () => {
  it("requires a nonblank name before submitting evidence", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderForm();

    await user.type(screen.getByLabelText("Name"), "   ");
    await user.click(screen.getByRole("button", { name: "Save evidence" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Evidence name is required.");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("requires the selected reference payload and normalizes DMS submissions", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderForm();

    await user.type(screen.getByLabelText("Name"), "Vendor SOC report");
    await user.click(screen.getByRole("button", { name: "Save evidence" }));
    expect(screen.getByRole("alert")).toHaveTextContent("A DMS document UUID is required.");
    expect(onSubmit).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("DMS document UUID"), "document-9");
    await user.click(screen.getByRole("button", { name: "Save evidence" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0]?.[0]).toMatchObject({
      name: "Vendor SOC report",
      description: "",
      evidence_type: "document",
      classification: "internal",
      collection_method: "manual",
      reference_kind: "dms_document",
      document_id: "document-9",
      external_uri: "",
      text_reference: "",
      sha256: "",
    });
  });

  it("requires external URL references and strips inactive reference fields", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderForm({ initial: baseEvidence });

    await user.selectOptions(screen.getByLabelText("Reference kind"), "external_url");
    await user.clear(screen.getByLabelText("External URL"));
    await user.click(screen.getByRole("button", { name: "Save evidence" }));
    expect(screen.getByRole("alert")).toHaveTextContent("An external URL is required.");
    expect(onSubmit).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("External URL"), "https://example.invalid/new.pdf");
    await user.click(screen.getByRole("button", { name: "Save evidence" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0]?.[0]).toMatchObject({
      reference_kind: "external_url",
      document_id: null,
      external_uri: "https://example.invalid/new.pdf",
      text_reference: "",
    });
  });

  it("treats whitespace-only external URLs as missing", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderForm({
      initial: {
        ...baseEvidence,
        reference_kind: "external_url",
        external_uri: undefined,
      },
    });

    expect(screen.getByLabelText("External URL")).toHaveValue("");
    await user.type(screen.getByLabelText("External URL"), "   ");
    await user.click(screen.getByRole("button", { name: "Save evidence" }));

    expect(screen.getByRole("alert")).toHaveTextContent("An external URL is required.");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("requires text references and blocks inverted validity windows", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderForm({ initial: baseEvidence });

    await user.selectOptions(screen.getByLabelText("Reference kind"), "text_reference");
    await user.clear(screen.getByLabelText("Text reference"));
    await user.click(screen.getByRole("button", { name: "Save evidence" }));
    expect(screen.getByRole("alert")).toHaveTextContent("A text reference is required.");
    expect(onSubmit).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Text reference"), "Owner attestation retained.");
    await user.clear(screen.getByLabelText("Valid until"));
    await user.type(screen.getByLabelText("Valid until"), "2026-06-30T00:00");
    await user.click(screen.getByRole("button", { name: "Save evidence" }));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Valid-until must be later than valid-from."
    );
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("treats whitespace-only text references as missing", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderForm({
      initial: {
        ...baseEvidence,
        reference_kind: "text_reference",
        text_reference: undefined,
      },
    });

    expect(screen.getByLabelText("Text reference")).toHaveValue("");
    await user.type(screen.getByLabelText("Text reference"), "   ");
    await user.click(screen.getByRole("button", { name: "Save evidence" }));

    expect(screen.getByRole("alert")).toHaveTextContent("A text reference is required.");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("rejects validity windows where the end equals the start", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderForm({ initial: baseEvidence });

    await user.clear(screen.getByLabelText("Valid until"));
    await user.type(screen.getByLabelText("Valid until"), "2026-07-01T00:00");
    await user.click(screen.getByRole("button", { name: "Save evidence" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Valid-until must be later than valid-from."
    );
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("allows one-sided validity windows", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderForm({
      initial: {
        ...baseEvidence,
        valid_until: null,
      },
    });

    expect(screen.getByLabelText("Collected at")).toHaveValue("2026-07-20T10:00");
    expect(screen.getByLabelText("Valid from")).toHaveValue("2026-07-01T00:00");
    expect(screen.getByLabelText("Valid until")).toHaveValue("");
    await user.click(screen.getByRole("button", { name: "Save evidence" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0]?.[0]).toMatchObject({
      valid_from: "2026-07-01T00:00:00.000Z",
      valid_until: null,
    });
  });

  it("renders field-specific server validation errors", () => {
    const error = {
      details: {
        error: {
          field_errors: [
            { field: "name", code: "required", message: "Name rejected" },
            { field: "document_id", code: "invalid", message: "Document rejected" },
            { field: "valid_until", code: "range", message: "Date rejected" },
          ],
        },
      },
    };

    renderForm({ initial: baseEvidence, error });

    expect(screen.getByText("Name rejected")).toBeVisible();
    expect(screen.getByText("Document rejected")).toBeVisible();
    expect(screen.getByText("Date rejected")).toBeVisible();
  });

  it("renders field-specific reference errors for external and text references", () => {
    const error = {
      details: {
        error: {
          field_errors: [
            { field: "external_uri", code: "invalid", message: "URL rejected" },
            { field: "text_reference", code: "invalid", message: "Text rejected" },
          ],
        },
      },
    };

    const { unmount } = renderForm({
      initial: { ...baseEvidence, reference_kind: "external_url" },
      error,
    });
    expect(screen.getByText("URL rejected")).toBeVisible();

    unmount();
    renderForm({ initial: { ...baseEvidence, reference_kind: "text_reference" }, error });
    expect(screen.getByText("Text rejected")).toBeVisible();
  });

  it("submits text references with ISO dates and preserves operator-entered metadata", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderForm({ initial: baseEvidence });

    await user.selectOptions(screen.getByLabelText("Type"), "attestation");
    await user.selectOptions(screen.getByLabelText("Classification"), "restricted");
    await user.selectOptions(screen.getByLabelText("Reference kind"), "text_reference");
    await user.clear(screen.getByLabelText("Text reference"));
    await user.type(screen.getByLabelText("Text reference"), "Owner attestation retained.");
    await user.clear(screen.getByLabelText("Description"));
    await user.type(screen.getByLabelText("Description"), "Updated assurance note");
    await user.clear(screen.getByLabelText("Valid until"));
    await user.type(screen.getByLabelText("Valid until"), "2027-01-31T12:30");
    await user.click(screen.getByRole("button", { name: "Save evidence" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0]?.[0]).toMatchObject({
      name: "SOC report",
      description: "Updated assurance note",
      evidence_type: "attestation",
      reference_kind: "text_reference",
      classification: "restricted",
      document_id: null,
      external_uri: "",
      text_reference: "Owner attestation retained.",
      valid_from: "2026-07-01T00:00:00.000Z",
      valid_until: new Date("2027-01-31T12:30").toISOString(),
    });
  });

  it("disables save and cancel actions while a submission is pending", async () => {
    const user = userEvent.setup();
    const { onCancel, onSubmit } = renderForm({ initial: baseEvidence, pending: true });

    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onCancel).not.toHaveBeenCalled();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
