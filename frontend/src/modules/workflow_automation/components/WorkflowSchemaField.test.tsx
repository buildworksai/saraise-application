import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
/* eslint-disable max-lines-per-function -- Field component tests cover each schema kind in one cohesive render contract. */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { JsonValue, UISchemaField } from "../contracts";
import { workflowService } from "../services/workflow-service";
import { WorkflowSchemaField } from "./WorkflowSchemaField";

function renderField(
  field: UISchemaField,
  value: JsonValue | undefined = undefined,
  onChange = vi.fn<(value: JsonValue) => void>()
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <WorkflowSchemaField field={field} value={value} onChange={onChange} />
    </QueryClientProvider>
  );
  return { ...view, onChange };
}

describe("WorkflowSchemaField", () => {
  beforeEach(() => {
    vi.spyOn(workflowService.catalog, "lookup").mockResolvedValue([
      { id: "role-1", label: "Purchasing managers", description: null, kind: "role" },
    ]);
  });

  afterEach(() => vi.restoreAllMocks());

  it("renders boolean fields as checked only for true values", async () => {
    const user = userEvent.setup();
    const { onChange, rerender } = renderField(
      { kind: "boolean", key: "enabled", label: "Enabled", required: false },
      true
    );

    expect(screen.getByLabelText("Enabled")).toBeChecked();
    await user.click(screen.getByLabelText("Enabled"));
    expect(onChange).toHaveBeenCalledWith(false);

    rerender(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <WorkflowSchemaField
          field={{ kind: "boolean", key: "enabled", label: "Enabled", required: false }}
          value="true"
          onChange={onChange}
        />
      </QueryClientProvider>
    );
    expect(screen.getByLabelText("Enabled")).not.toBeChecked();
  });

  it("renders select fields with required metadata and emits string values", async () => {
    const user = userEvent.setup();
    const { onChange } = renderField(
      {
        kind: "select",
        key: "mode",
        label: "Mode",
        required: true,
        options: [{ value: "strict", label: "Strict" }],
      },
      42
    );

    const select = screen.getByLabelText("Mode");
    expect(select).toBeRequired();
    expect(select).toHaveValue("");
    expect(select).toHaveTextContent("Select…");
    await user.selectOptions(select, "strict");
    expect(onChange).toHaveBeenCalledWith("strict");

    renderField(
      {
        kind: "select",
        key: "strict-mode",
        label: "Strict mode",
        required: false,
        options: [{ value: "strict", label: "Strict" }],
      },
      "strict"
    );
    expect(screen.getByLabelText("Strict mode")).toHaveValue("strict");
  });

  it("renders lookup fields from the governed catalog and disables on outage", async () => {
    const user = userEvent.setup();
    const { onChange } = renderField(
      { kind: "lookup", key: "target", label: "Target", required: true, lookup_key: "targets" },
      "role-1"
    );

    const lookup = await screen.findByLabelText("Target");
    await waitFor(() => expect(lookup).not.toBeDisabled());
    expect(workflowService.catalog.lookup).toHaveBeenCalledWith("targets");
    expect(lookup).toHaveValue("role-1");
    await user.selectOptions(lookup, "role-1");
    expect(onChange).toHaveBeenCalledWith("role-1");

    vi.mocked(workflowService.catalog.lookup).mockRejectedValueOnce(new Error("Lookup failed"));
    renderField(
      { kind: "lookup", key: "owner", label: "Owner", required: false, lookup_key: "owners" },
      123
    );
    const failedLookup = screen.getByLabelText("Owner");
    await waitFor(() => expect(failedLookup).toHaveTextContent("Lookup unavailable"));
    expect(failedLookup).toBeDisabled();
    expect(failedLookup).toHaveTextContent("Lookup unavailable");
    expect(failedLookup).toHaveValue("");

    renderField(
      { kind: "lookup", key: "backup", label: "Backup", required: false, lookup_key: "targets" },
      false
    );
    await waitFor(() => expect(screen.getByLabelText("Backup")).not.toBeDisabled());
    expect(screen.getByLabelText("Backup")).toHaveValue("");
  });

  it("renders text and number fields with kind-specific attributes and coerces number changes", () => {
    const text = renderField(
      {
        kind: "text",
        key: "path",
        label: "Context path",
        required: true,
        placeholder: "actor.id",
      },
      false
    );
    expect(screen.getByLabelText("Context path")).toHaveAttribute("type", "text");
    expect(screen.getByLabelText("Context path")).toHaveAttribute("placeholder", "actor.id");
    expect(screen.getByLabelText("Context path")).not.toHaveAttribute("min");
    expect(screen.getByLabelText("Context path")).not.toHaveAttribute("max");
    expect(screen.getByLabelText("Context path")).toHaveValue("");
    fireEvent.change(screen.getByLabelText("Context path"), { target: { value: "entity.id" } });
    expect(text.onChange).toHaveBeenLastCalledWith("entity.id");

    renderField(
      {
        kind: "text",
        key: "existing-path",
        label: "Existing path",
        required: false,
      },
      "actor.id"
    );
    expect(screen.getByLabelText("Existing path")).toHaveValue("actor.id");

    const number = renderField(
      {
        kind: "number",
        key: "limit",
        label: "Limit",
        required: true,
        minimum: 1,
        maximum: 10,
      },
      3
    );
    expect(screen.getByLabelText("Limit")).toHaveAttribute("type", "number");
    expect(screen.getByLabelText("Limit")).toHaveAttribute("min", "1");
    expect(screen.getByLabelText("Limit")).toHaveAttribute("max", "10");
    expect(screen.getByLabelText("Limit")).not.toHaveAttribute("placeholder");
    expect(screen.getByLabelText("Limit")).toHaveValue(3);
    fireEvent.change(screen.getByLabelText("Limit"), { target: { value: "8" } });
    expect(number.onChange).toHaveBeenLastCalledWith(8);
  });
});
