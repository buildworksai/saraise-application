import { describe, expect, it } from "vitest";
import { nextCronRuns } from "../../components/CronPreview";

describe("cron preview", () => {
  it("returns five ordered future occurrences", () => {
    const runs = nextCronRuns("*/15 * * * *", "UTC");
    expect(runs).toHaveLength(5);
    expect(runs.every((run, index) => index === 0 || run > runs[index - 1]!)).toBe(true);
  });

  it("rejects malformed expressions without fabricating dates", () => {
    expect(nextCronRuns("invalid cron", "UTC")).toEqual([]);
  });
});
