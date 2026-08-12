import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { exportTimeseriesToCSV, exportToCSV } from "./export";

describe("export utilities", () => {
  const createObjectURL = vi.fn<(blob: Blob) => string>(() => "blob:export");
  const revokeObjectURL = vi.fn();
  let clickSpy: ReturnType<typeof vi.spyOn>;
  class FakeBlob {
    constructor(
      private readonly parts: string[],
      public readonly options?: BlobPropertyBag
    ) {}

    text() {
      return Promise.resolve(this.parts.join(""));
    }
  }

  beforeEach(() => {
    createObjectURL.mockClear();
    revokeObjectURL.mockClear();
    vi.stubGlobal("Blob", FakeBlob as unknown as typeof Blob);
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  });

  afterEach(() => {
    clickSpy.mockRestore();
    vi.unstubAllGlobals();
  });

  it("exports typed rows with escaped scalar, object, null, and unsupported values", async () => {
    let exportedBlob: Blob | undefined;
    createObjectURL.mockImplementation((blob: Blob) => {
      exportedBlob = blob;
      return "blob:export";
    });

    exportToCSV(
      [
        {
          name: 'Widget, "A"',
          active: true,
          count: 7,
          payload: { tier: "gold" },
          missing: null,
          callback: () => undefined,
        },
      ],
      "inventory-export",
      ["name", "active", "count", "payload", "missing", "callback"]
    );

    expect(clickSpy).toHaveBeenCalledOnce();
    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:export");
    expect(exportedBlob).toBeDefined();
    await expect(exportedBlob?.text()).resolves.toBe(
      'name,active,count,payload,missing,callback\n"Widget, ""A""",true,7,"{""tier"":""gold""}",,'
    );
  });

  it("does not create a download for empty datasets", () => {
    exportToCSV([], "empty-export");

    expect(createObjectURL).not.toHaveBeenCalled();
    expect(clickSpy).not.toHaveBeenCalled();
  });

  it("exports timeseries values with stable default filename and blank null samples", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-08T10:00:00Z"));
    let exportedBlob: Blob | undefined;
    let downloadName = "";
    createObjectURL.mockImplementation((blob: Blob) => {
      exportedBlob = blob;
      return "blob:timeseries";
    });
    clickSpy.mockImplementation(function click(this: HTMLAnchorElement) {
      downloadName = this.download;
    });

    exportTimeseriesToCSV(
      [
        { date: "2026-08-07", timestamp: "2026-08-07T00:00:00Z", value: 12 },
        { date: "2026-08-08", timestamp: "2026-08-08T00:00:00Z", value: null },
      ],
      "latency"
    );

    expect(downloadName).toBe("latency_timeseries_2026-08-08.csv");
    await expect(exportedBlob?.text()).resolves.toBe(
      "Date,Timestamp,Value\n2026-08-07,2026-08-07T00:00:00Z,12\n2026-08-08,2026-08-08T00:00:00Z,"
    );
    vi.useRealTimers();
  });
});
