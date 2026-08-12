import { describe, expect, it } from "vitest";
import { fixedAdd } from "./math";

describe("fixed decimal arithmetic", () => {
  it("adds signed four-decimal values without binary floating point", () => {
    expect(fixedAdd(["0.1000", "0.2000"])).toBe("0.3000");
    expect(fixedAdd(["100.0000", "-40.1255", "-59.8745"])).toBe("0.0000");
  });

  it("preserves negative totals and normalizes whitespace-padded signed values", () => {
    expect(fixedAdd(["  -1.2500", "0.1250"])).toBe("-1.1250");
    expect(fixedAdd(["-.5000", "+.1250"])).toBe("-0.3750");
  });

  it("handles empty collections and integer-only monetary strings", () => {
    expect(fixedAdd([])).toBe("0.0000");
    expect(fixedAdd(["12", "-5"])).toBe("7.0000");
  });

  it("truncates extra decimal precision to the fixed four-decimal scale", () => {
    expect(fixedAdd(["1.99999", "0.00001"])).toBe("1.9999");
  });
});
