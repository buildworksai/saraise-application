import { describe, expect, it } from "vitest";
import type { FieldDefinition, FieldType, JSONValue } from "../contracts";
import { validateDynamicValues } from "./dynamic-validation";

function field(field_type: FieldType, overrides: Partial<FieldDefinition> = {}): FieldDefinition {
  return { id: `${field_type}-id`, name: field_type, key: field_type, field_type, is_required: false, is_read_only: false, is_searchable: false, default_value: null, validation_rules: {}, options: field_type === "select" ? ["open", "closed"] : [], reference_entity_code: field_type === "reference" ? "target" : null, help_text: "", placeholder: "", order: 1, created_at: "2026-01-01T00:00:00Z", ...overrides };
}

describe("dynamic form client validation", () => {
  it.each<[FieldType, JSONValue]>([["text", "hello"], ["number", 12], ["date", "2026-07-23"], ["boolean", false], ["select", "open"], ["reference", "00000000-0000-0000-0000-000000000001"], ["json", { nested: true }]])("accepts a valid %s value", (type, value) => {
    expect(validateDynamicValues([field(type)], { [type]: value })).toEqual({});
  });

  it("preserves false and zero while rejecting missing required values", () => {
    expect(validateDynamicValues([field("boolean", { is_required: true })], { boolean: false })).toEqual({});
    expect(validateDynamicValues([field("number", { is_required: true })], { number: 0 })).toEqual({});
    expect(validateDynamicValues([field("text", { is_required: true })], {})).toEqual({ text: "This field is required." });
  });

  it("rejects malformed built-in values before server validation", () => {
    expect(validateDynamicValues([field("select")], { select: "missing" })).toHaveProperty("select");
    expect(validateDynamicValues([field("date")], { date: "23/07/2026" })).toHaveProperty("date");
    expect(validateDynamicValues([field("number")], { number: "12" })).toHaveProperty("number");
    expect(validateDynamicValues([field("json")], { json: "{" })).toHaveProperty("json");
  });
});
