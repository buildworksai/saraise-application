import { describe, expect, it, vi } from "vitest";
import { formatDate, formatDuration, newTransitionKey } from "./workflow-utils";

describe("workflow-utils", () => {
  it("formats missing and invalid dates as absent evidence", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate("not-a-date")).toBe("—");
  });

  it("formats valid dates with explicit medium date and short time evidence", () => {
    const originalDateTimeFormat = Intl.DateTimeFormat;
    const format = vi.fn(() => "formatted-date");
    const dateTimeFormat = vi.fn(function DateTimeFormat(
      _locales?: Intl.LocalesArgument,
      _options?: Intl.DateTimeFormatOptions
    ): Intl.DateTimeFormat {
      void _locales;
      void _options;
      return { format } as unknown as Intl.DateTimeFormat;
    });
    Object.defineProperty(Intl, "DateTimeFormat", {
      configurable: true,
      value: dateTimeFormat,
    });

    try {
      expect(formatDate("2026-07-22T00:00:00Z")).toBe("formatted-date");
      expect(dateTimeFormat).toHaveBeenCalledWith(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      });
    } finally {
      Object.defineProperty(Intl, "DateTimeFormat", {
        configurable: true,
        value: originalDateTimeFormat,
      });
    }
  });

  it("formats missing, second-level, and minute-level durations", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-22T00:00:04Z"));
    expect(formatDuration(null, null, 60000)).toBe("—");
    expect(formatDuration("2026-07-22T00:00:00Z", null, 60000)).toBe("4s");
    expect(formatDuration("2026-07-22T00:00:00Z", "2026-07-22T00:02:04Z", 60000)).toBe("2m 4s");
    vi.useRealTimers();
  });

  it("formats invalid, future, and threshold duration boundaries", () => {
    expect(formatDuration("not-a-date", null, 60000)).toBe("—");
    expect(formatDuration("2026-07-22T00:00:00Z", "not-a-date", 60000)).toBe("—");
    expect(formatDuration("2026-07-22T00:00:00Z", "2026-07-22T00:00:01Z", 0)).toBe("—");
    expect(formatDuration("2026-07-22T00:00:00Z", "2026-07-22T00:00:01Z", Number.NaN)).toBe("—");
    expect(formatDuration("2026-07-22T00:01:00Z", "2026-07-22T00:00:00Z", 60000)).toBe("0s");
    expect(formatDuration("2026-07-22T00:00:00Z", "2026-07-22T00:00:59.999Z", 60000)).toBe("59s");
    expect(formatDuration("2026-07-22T00:00:00Z", "2026-07-22T00:01:00Z", 60000)).toBe("1m 0s");
    expect(formatDuration("2026-07-22T00:00:00Z", "2026-07-22T00:01:01Z", 60000)).toBe("1m 1s");
  });

  it("prefixes idempotent transition keys", () => {
    expect(newTransitionKey("publish")).toMatch(/^publish:/u);
  });
});
