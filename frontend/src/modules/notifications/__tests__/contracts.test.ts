import { describe, expect, it } from "vitest";
import { ENDPOINTS, MODULE_API_PREFIX, PATHS } from "../contracts";

describe("notification v2 contracts", () => {
  it("owns only canonical governed endpoints", () => {
    expect(MODULE_API_PREFIX).toBe("/api/v2/notifications");
    const serialized = JSON.stringify(ENDPOINTS);
    expect(serialized).not.toContain("/api/v1");
    expect(ENDPOINTS.INBOX.MARK_UNREAD("id with space")).toContain("id%20with%20space/mark-unread/");
    expect(ENDPOINTS.TEMPLATES.PREVIEW_DRAFT).toBe("/api/v2/notifications/templates/preview-draft/");
    expect(ENDPOINTS.CONFIGURATION.EXPORT("production")).toBe("/api/v2/notifications/configuration/production/export/");
  });

  it("declares every brief-owned page path", () => {
    expect(Object.keys(PATHS)).toHaveLength(16);
    expect(PATHS.TEMPLATE_EDIT(":id")).toBe("/notifications/templates/:id/edit");
    expect(PATHS.CONFIGURATION_HISTORY).toBe("/notifications/configuration/history");
  });
});
