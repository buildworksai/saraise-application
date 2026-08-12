import { describe, expect, it } from "vitest";
import type { UISchemaField } from "../contracts";
import {
  inputClass,
  inputMax,
  inputMin,
  inputPlaceholder,
  inputType,
  scalarFieldValue,
  stringFieldValue,
  workflowCatalogLookupKey,
} from "./workflow-schema-field-utils";

const numberField: UISchemaField = {
  kind: "number",
  key: "limit",
  label: "Limit",
  required: true,
  minimum: 1,
  maximum: 10,
};

const textField: UISchemaField = {
  kind: "text",
  key: "path",
  label: "Path",
  required: true,
  placeholder: "actor.id",
};

describe("workflow schema field utilities", () => {
  it("defines stable input styling and lookup query keys", () => {
    expect(inputClass).toBe(
      "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    );
    expect(workflowCatalogLookupKey("targets")).toEqual(["workflow-catalog-lookup", "targets"]);
  });

  it("normalizes select and lookup values to strings only", () => {
    expect(stringFieldValue("role-1")).toBe("role-1");
    expect(stringFieldValue(123)).toBe("");
    expect(stringFieldValue(false)).toBe("");
    expect(stringFieldValue(undefined)).toBe("");
  });

  it("normalizes text and number input values to scalar form fields", () => {
    expect(scalarFieldValue("actor.id")).toBe("actor.id");
    expect(scalarFieldValue(3)).toBe(3);
    expect(scalarFieldValue(false)).toBe("");
    expect(scalarFieldValue(undefined)).toBe("");
  });

  it("derives input attributes by schema field kind", () => {
    expect(inputType(numberField)).toBe("number");
    expect(inputMin(numberField)).toBe(1);
    expect(inputMax(numberField)).toBe(10);
    expect(inputPlaceholder(numberField)).toBeUndefined();

    expect(inputType(textField)).toBe("text");
    expect(inputMin(textField)).toBeUndefined();
    expect(inputMax(textField)).toBeUndefined();
    expect(inputPlaceholder(textField)).toBe("actor.id");

    const textWithIgnoredBounds = { ...textField, minimum: 2, maximum: 8 } as UISchemaField;
    const numberWithIgnoredPlaceholder = {
      ...numberField,
      placeholder: "ignored",
    } as UISchemaField;

    expect(inputMin(textWithIgnoredBounds)).toBeUndefined();
    expect(inputMax(textWithIgnoredBounds)).toBeUndefined();
    expect(inputPlaceholder(numberWithIgnoredPlaceholder)).toBeUndefined();
  });
});
