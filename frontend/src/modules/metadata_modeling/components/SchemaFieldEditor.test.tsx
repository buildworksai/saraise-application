/* eslint-disable max-lines-per-function -- component editor coverage is grouped by field-type behavior. */
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type { FieldDefinitionInput } from "../contracts";
import { SchemaFieldEditor } from "./SchemaFieldEditor";

const baseField: FieldDefinitionInput = {
  name: "Serial number",
  key: "serial_number",
  field_type: "text",
  is_required: false,
  is_read_only: false,
  is_searchable: false,
  default_value: null,
  validation_rules: {},
  options: [],
  reference_entity_code: null,
  help_text: "",
  placeholder: "",
  order: 1,
};

describe("SchemaFieldEditor", () => {
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

  it("normalizes API keys, text validation rules, and boolean flags", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(<SchemaFieldEditor field={baseField} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText("API key"), { target: { value: "Asset Serial!" } });
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ key: "asset_serial_" }));

    fireEvent.change(screen.getByLabelText("Minimum length"), { target: { value: "3" } });
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ validation_rules: { min_length: 3 } })
    );

    fireEvent.change(screen.getByLabelText("Validation pattern"), {
      target: { value: "^[A-Z]+$" },
    });
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ validation_rules: { regex: "^[A-Z]+$" } })
    );

    await user.click(screen.getByLabelText("required"));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ is_required: true }));
  });

  it("resets incompatible field settings when the type changes", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(
      <SchemaFieldEditor
        field={{
          ...baseField,
          field_type: "reference",
          reference_entity_code: "asset",
          validation_rules: { min_length: 2 },
        }}
        onChange={onChange}
      />
    );

    await user.click(screen.getByRole("combobox", { name: "Field type" }));
    await user.click(
      within(await screen.findByRole("listbox")).getByRole("option", { name: "select" })
    );

    expect(onChange).toHaveBeenLastCalledWith({
      ...baseField,
      field_type: "select",
      validation_rules: {},
      options: [],
      reference_entity_code: null,
    });
  });

  it("parses default values and conditional settings for number, select, reference, and json fields", () => {
    const onChange = vi.fn();

    const { rerender } = render(
      <SchemaFieldEditor field={{ ...baseField, field_type: "number" }} onChange={onChange} />
    );
    fireEvent.change(screen.getByLabelText("Default value"), { target: { value: "42" } });
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ default_value: 42 }));
    fireEvent.change(screen.getByLabelText("Minimum"), { target: { value: "10" } });
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ validation_rules: { minimum: 10 } })
    );

    rerender(
      <SchemaFieldEditor field={{ ...baseField, field_type: "select" }} onChange={onChange} />
    );
    fireEvent.change(screen.getByLabelText("Options (comma separated)"), {
      target: { value: "Draft, Active, Archived" },
    });
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ options: ["Draft", "Active", "Archived"] })
    );

    rerender(
      <SchemaFieldEditor field={{ ...baseField, field_type: "reference" }} onChange={onChange} />
    );
    fireEvent.change(screen.getByLabelText("Published entity code"), {
      target: { value: "customer" },
    });
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ reference_entity_code: "customer" })
    );

    rerender(
      <SchemaFieldEditor field={{ ...baseField, field_type: "json" }} onChange={onChange} />
    );
    fireEvent.change(screen.getByLabelText("Default value"), {
      target: { value: '{"enabled":true}' },
    });
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ default_value: { enabled: true } })
    );
  });

  it("disables every editable control when the editor is locked", () => {
    render(<SchemaFieldEditor field={baseField} onChange={vi.fn()} disabled />);

    for (const control of screen.getAllByRole("textbox")) expect(control).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Field type" })).toBeDisabled();
    expect(screen.getByLabelText("required")).toBeDisabled();
  });
});
