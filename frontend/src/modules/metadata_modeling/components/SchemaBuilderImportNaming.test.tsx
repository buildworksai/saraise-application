/* eslint-disable max-lines-per-function -- cohesive metadata component flows share pointer shims and contract fixtures. */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type {
  ExportDocument,
  FieldDefinitionInput,
  JSONObject,
  NamingConfiguration,
  NamingStrategy,
} from "../contracts";
import { ImportSchemaDialog } from "./ImportSchemaDialog";
import { NamingStrategyEditor } from "./NamingStrategyEditor";
import { SchemaFieldBuilder } from "./SchemaFieldBuilder";

const field = (overrides: Partial<FieldDefinitionInput> = {}): FieldDefinitionInput => ({
  name: "Serial number",
  key: "serial_number",
  field_type: "text",
  is_required: true,
  is_read_only: false,
  is_searchable: true,
  default_value: null,
  validation_rules: {},
  options: [],
  reference_entity_code: null,
  help_text: "",
  placeholder: "",
  order: 1,
  ...overrides,
});
const fieldJson = (overrides: Partial<FieldDefinitionInput> = {}): JSONObject => {
  const value = field(overrides);
  return {
    name: value.name,
    key: value.key,
    field_type: value.field_type,
    is_required: value.is_required,
    is_read_only: value.is_read_only,
    is_searchable: value.is_searchable,
    default_value: value.default_value,
    validation_rules: {},
    options: [...value.options],
    reference_entity_code: value.reference_entity_code,
    help_text: value.help_text,
    placeholder: value.placeholder,
    order: value.order,
  };
};

const exportDocument: ExportDocument = {
  format_version: "metadata-modeling/v1",
  checksum: "sha256:1234567890abcdef",
  entity: {
    name: "Asset",
    plural_name: "Assets",
    code: "asset",
    description: "Tracked assets",
    icon: "box",
    is_submittable: true,
    track_changes: true,
    naming_strategy: "uuid",
    naming_config: {},
  },
  schema: {
    fields: [fieldJson()],
    change_summary: "Initial asset schema",
    based_on_version_id: null,
  },
};

describe("metadata modeling component coverage", () => {
  beforeAll(() => {
    if (!Element.prototype.hasPointerCapture) {
      Element.prototype.hasPointerCapture = () => false;
    }
    if (!Element.prototype.setPointerCapture) {
      Element.prototype.setPointerCapture = () => undefined;
    }
    if (!Element.prototype.releasePointerCapture) {
      Element.prototype.releasePointerCapture = () => undefined;
    }
    if (!Element.prototype.scrollIntoView) {
      Element.prototype.scrollIntoView = () => undefined;
    }
  });

  it("adds, reorders, edits, removes, and locks schema fields without mutating source arrays", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const fields = [
      field({ name: "Serial number", key: "serial_number", order: 1 }),
      field({ name: "Asset tag", key: "asset_tag", order: 2, is_required: false }),
    ];

    const { rerender } = render(<SchemaFieldBuilder fields={fields} onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: "Add field" }));
    expect(onChange).toHaveBeenLastCalledWith([
      ...fields,
      expect.objectContaining({ key: "", field_type: "text", order: 3 }),
    ]);

    await user.click(screen.getAllByRole("button", { name: "Move field down" })[0]!);
    expect(onChange).toHaveBeenLastCalledWith([
      expect.objectContaining({ key: "asset_tag", order: 1 }),
      expect.objectContaining({ key: "serial_number", order: 2 }),
    ]);

    fireEvent.change(screen.getAllByLabelText("Label")[0]!, {
      target: { value: "Serial ID" },
    });
    expect(onChange).toHaveBeenLastCalledWith(
      expect.arrayContaining([expect.objectContaining({ name: "Serial ID" })])
    );

    await user.click(screen.getAllByRole("button", { name: "Remove field" })[0]!);
    expect(onChange).toHaveBeenLastCalledWith([
      expect.objectContaining({ key: "asset_tag", order: 1 }),
    ]);
    expect(fields[0]?.order).toBe(1);

    rerender(<SchemaFieldBuilder fields={[]} onChange={onChange} />);
    expect(screen.getByText(/No fields yet/u)).toBeInTheDocument();

    rerender(<SchemaFieldBuilder fields={fields} onChange={onChange} disabled />);
    expect(screen.getByRole("button", { name: "Add field" })).toBeDisabled();
    for (const button of screen.getAllByRole("button", { name: /Move field|Remove field/u })) {
      expect(button).toBeDisabled();
    }
  });

  it("validates import documents before closing the dialog", async () => {
    const onImport = vi.fn().mockResolvedValue(undefined);
    const onOpenChange = vi.fn();

    render(<ImportSchemaDialog open onOpenChange={onOpenChange} onImport={onImport} />);

    const upload = screen.getByLabelText("Schema JSON document");
    fireEvent.change(upload, {
      target: {
        files: [
          {
            text: vi
              .fn()
              .mockResolvedValue(JSON.stringify({ format_version: "metadata-modeling/v1" })),
          },
        ],
      },
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(/missing format_version/u);
    expect(screen.getByRole("button", { name: "Validate import" })).toBeDisabled();

    fireEvent.change(upload, {
      target: {
        files: [{ text: vi.fn().mockResolvedValue(JSON.stringify(exportDocument)) }],
      },
    });
    expect(await screen.findByText(/sha256:12345/u)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Validate import" }));
    await waitFor(() =>
      expect(onImport).toHaveBeenCalledWith({ document: exportDocument, mode: "validate_only" })
    );
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("switches naming strategies and emits only valid strategy configuration", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const config: NamingConfiguration = {};

    const { rerender } = render(
      <NamingStrategyEditor
        strategy="uuid"
        config={config}
        fields={[field({ key: "serial_number", is_read_only: true })]}
        onChange={onChange}
      />
    );

    await user.click(screen.getByRole("combobox", { name: "Strategy" }));
    await user.click(
      within(await screen.findByRole("listbox")).getByRole("option", { name: "Sequence" })
    );
    expect(onChange).toHaveBeenCalledWith("sequence", {});

    rerender(
      <NamingStrategyEditor
        strategy={"sequence" satisfies NamingStrategy}
        config={{ prefix_template: "AST-{YYYY}-{#####}", padding: 5 }}
        fields={[]}
        onChange={onChange}
      />
    );
    fireEvent.change(screen.getByLabelText("Prefix template"), {
      target: { value: "PO-{YYYY}-{######}" },
    });
    expect(onChange).toHaveBeenLastCalledWith("sequence", {
      prefix_template: "PO-{YYYY}-{######}",
      padding: 5,
    });
    fireEvent.change(screen.getByLabelText("Padding"), { target: { value: "8" } });
    expect(onChange).toHaveBeenLastCalledWith("sequence", {
      prefix_template: "AST-{YYYY}-{#####}",
      padding: 8,
    });

    rerender(
      <NamingStrategyEditor
        strategy="field"
        config={{}}
        fields={[
          field({ key: "mutable", is_required: true, is_read_only: false }),
          field({ key: "asset_tag", is_required: true, is_read_only: true }),
        ]}
        onChange={onChange}
      />
    );
    await user.click(screen.getByRole("combobox", { name: "Required read-only field" }));
    const options = within(await screen.findByRole("listbox")).getAllByRole("option");
    expect(options.map((option) => option.textContent)).toEqual(["asset_tag"]);
    await user.click(options[0]!);
    expect(onChange).toHaveBeenLastCalledWith("field", { field_key: "asset_tag" });
  });
});
