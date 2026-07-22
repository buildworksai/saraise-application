import { describe, expect, it } from "vitest";
import { fixedAdd } from "./math";

describe("fixed decimal arithmetic", () => {
  it("adds signed four-decimal values without binary floating point", () => {
    expect(fixedAdd(["0.1000", "0.2000"])).toBe("0.3000");
    expect(fixedAdd(["100.0000", "-40.1255", "-59.8745"])).toBe("0.0000");
  });
});
