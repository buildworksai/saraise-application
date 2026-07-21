import type { JSONObject, JSONValue } from "../contracts";

export function formatDate(value: string | null): string {
  return value
    ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value))
    : "—";
}

export function parseJSON(value: string): JSONValue {
  return JSON.parse(value) as JSONValue;
}

export function asObject(value: JSONValue): JSONObject {
  if (value === null || Array.isArray(value) || typeof value !== "object") throw new Error("Use a JSON object.");
  return value;
}
