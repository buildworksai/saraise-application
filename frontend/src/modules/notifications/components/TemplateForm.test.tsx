/* eslint-disable max-lines-per-function -- form workflow tests intentionally keep user steps explicit. */
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/api-client";
import type { TemplateCreateInput, TemplatePreviewResult } from "../contracts";
import { TemplateForm, asVersionInput } from "./TemplateForm";

const previewResult: TemplatePreviewResult = {
  subject: "Build completed",
  body: "Hello Asha",
  content_type: "text/plain",
  diagnostics: [{ level: "info", variable: "name", message: "Example value used." }],
};

function renderForm({
  initial,
  pending = false,
  error = null,
  onPreview = vi.fn().mockResolvedValue(previewResult),
  onSubmit = vi.fn().mockResolvedValue(undefined),
}: {
  readonly initial?: Partial<TemplateCreateInput>;
  readonly pending?: boolean;
  readonly error?: unknown;
  readonly onPreview?: (draft: TemplateCreateInput) => Promise<TemplatePreviewResult>;
  readonly onSubmit?: (draft: TemplateCreateInput) => Promise<void>;
} = {}) {
  render(
    <TemplateForm
      initial={initial}
      pending={pending}
      error={error}
      submitLabel="Save template"
      onPreview={onPreview}
      onSubmit={onSubmit}
    />
  );
  return { onPreview, onSubmit };
}

async function fillValidInAppDraft() {
  await userEvent.type(screen.getByLabelText("Code"), "security.alert");
  await userEvent.type(screen.getByLabelText("Name"), "Security alert");
  await userEvent.type(screen.getByLabelText("Category"), "security");
  fireEvent.change(screen.getByLabelText("Body template"), {
    target: { value: "Hello {{ name }}" },
  });
}

function variablesSchemaField(): HTMLTextAreaElement {
  const label = screen.getByText("Variables schema").closest("label");
  const textarea = label?.querySelector("textarea");
  if (!(textarea instanceof HTMLTextAreaElement)) {
    throw new Error("Variables schema textarea was not rendered.");
  }
  return textarea;
}

describe("TemplateForm governed workflow", () => {
  beforeEach(() => vi.clearAllMocks());

  it("blocks save until the server preview succeeds and submits the previewed draft", async () => {
    const { onPreview, onSubmit } = renderForm();

    expect(screen.getByRole("button", { name: /save template/i })).toBeDisabled();
    await fillValidInAppDraft();
    expect(screen.getByRole("button", { name: /preview/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /save template/i })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: /preview/i }));
    expect(await screen.findByText("Hello Asha")).toBeInTheDocument();
    expect(screen.getByText("info:")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /save template/i })).toBeEnabled();

    await userEvent.click(screen.getByRole("button", { name: /save template/i }));
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith({
        code: "security.alert",
        name: "Security alert",
        category: "security",
        channel: "in_app",
        locale: "en",
        subject_template: "",
        body_template: "Hello {{ name }}",
        variables_schema: {
          name: { type: "string", required: true, example: "Asha" },
        },
        content_type: "text/plain",
      })
    );
    expect(onPreview).toHaveBeenCalledTimes(1);
  });

  it("enforces channel-specific subject requirements and valid JSON schema", async () => {
    const { onPreview, onSubmit } = renderForm();

    await fillValidInAppDraft();
    fireEvent.change(screen.getByLabelText("Channel"), { target: { value: "email" } });
    expect(await screen.findByText("Email templates require a subject.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /preview/i })).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Subject template"), "Security alert");
    expect(screen.queryByText("Email templates require a subject.")).not.toBeInTheDocument();
    fireEvent.change(variablesSchemaField(), { target: { value: "[" } });
    expect(await screen.findByText("Variables schema must be valid JSON.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /preview/i })).toBeDisabled();

    fireEvent.change(variablesSchemaField(), { target: { value: "[]" } });
    expect(await screen.findByText("Variables schema must be a JSON object.")).toBeInTheDocument();
    fireEvent.change(variablesSchemaField(), {
      target: { value: '{ "name": { "type": "string", "required": true } }' },
    });
    await userEvent.click(screen.getByRole("button", { name: /preview/i }));
    await screen.findByText("Hello Asha");
    await userEvent.click(screen.getByRole("button", { name: /save template/i }));

    expect(onPreview).toHaveBeenCalledWith(
      expect.objectContaining({
        channel: "email",
        subject_template: "Security alert",
        variables_schema: { name: { type: "string", required: true } },
      })
    );
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("keeps immutable initial fields disabled and surfaces preview/save failures", async () => {
    const onPreview = vi
      .fn()
      .mockRejectedValueOnce(
        new ApiError("Sandbox unavailable", 503, undefined, "sandbox_down", "corr-preview")
      )
      .mockResolvedValueOnce({ ...previewResult, diagnostics: [] });
    const error = new ApiError("Version conflict", 409, undefined, "version_conflict", "corr-save");
    renderForm({
      initial: {
        code: "billing.receipt",
        name: "Billing receipt",
        category: "billing",
        channel: "email",
        locale: "en",
        subject_template: "Receipt",
        body_template: "Paid {{ amount }}",
        variables_schema: { amount: { type: "number", required: true, example: 42 } },
        content_type: "text/html",
      },
      error,
      onPreview,
    });

    expect(screen.getByLabelText("Code")).toBeDisabled();
    expect(screen.getByLabelText("Channel")).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent("Version conflict");

    await userEvent.click(screen.getByRole("button", { name: /preview/i }));
    expect(await screen.findByText("Sandbox unavailable")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /preview/i }));
    expect(await screen.findByText("No variable diagnostics.")).toBeInTheDocument();
    expect(screen.getByText("Build completed")).toBeInTheDocument();
  });
});

describe("template version projection", () => {
  it("drops create-only identity fields before version writes", () => {
    expect(
      asVersionInput({
        code: "ops.notice",
        name: "Ops notice",
        category: "operations",
        channel: "in_app",
        locale: "en",
        subject_template: "",
        body_template: "Deploy completed",
        variables_schema: {},
        content_type: "text/plain",
      })
    ).toEqual({
      name: "Ops notice",
      category: "operations",
      subject_template: "",
      body_template: "Deploy completed",
      variables_schema: {},
      content_type: "text/plain",
    });
  });
});
