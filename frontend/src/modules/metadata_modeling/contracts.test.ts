import { describe, expect, it } from "vitest";
import { ENDPOINTS, ROUTES } from "./contracts";

describe("metadata modeling API contract", () => {
  it("keeps every endpoint on governed API v2 and encodes identifiers", () => {
    const paths = [ENDPOINTS.entityDefinitions, ENDPOINTS.entityDefinition("id/unsafe"), ENDPOINTS.schemaVersions("entity"), ENDPOINTS.resources, ENDPOINTS.resource("record"), ENDPOINTS.namingSequences, ENDPOINTS.health, ENDPOINTS.configuration, ENDPOINTS.previewConfiguration, ENDPOINTS.configurationVersions, ENDPOINTS.rollbackConfiguration(3), ENDPOINTS.importConfiguration, ENDPOINTS.exportConfiguration];
    expect(paths.every((path) => path.startsWith("/api/v2/metadata-modeling/"))).toBe(true);
    expect(ENDPOINTS.entityDefinition("id/unsafe")).toContain("id%2Funsafe");
  });

  it("centralizes every frontend path", () => {
    expect(ROUTES.schemaDetail("id/unsafe")).toBe("/metadata-modeling/schemas/id%2Funsafe");
    expect(ROUTES.recordCreateFor("entity id")).toBe("/metadata-modeling/records/new?entity=entity%20id");
    expect(ROUTES.settings).toBe("/metadata-modeling/settings");
  });
});
