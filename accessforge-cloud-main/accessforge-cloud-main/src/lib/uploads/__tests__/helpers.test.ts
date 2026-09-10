import { describe, expect, it } from "vitest";

import { detectKind } from "../helpers";

/**
 * `detectKind` is the CLIENT-side gate: ModuleRunner refuses to even append a
 * file to the FormData when its kind is not in the module's `acceptedKinds`, so
 * a mis-detected extension is rejected before the server allowlist ever sees
 * it. `.xlsb` was missing here, which blocked binary MPD RSD workbooks in the
 * browser regardless of what the backend accepted.
 */
describe("detectKind", () => {
  it("classifies every Excel workbook format as excel", () => {
    for (const name of ["book.xlsx", "book.xls", "MPD RSD.xlsb"]) {
      // Empty type: a browser with no Office install reports no MIME for
      // .xlsb, so the extension is the only signal available.
      expect(detectKind(new File([""], name, { type: "" })), name).toBe("excel");
    }
  });

  it("is case-insensitive about the extension", () => {
    expect(detectKind(new File([""], "MPD_RSD.XLSB", { type: "" }))).toBe("excel");
  });

  it("still uses the declared MIME when the extension is unknown", () => {
    const file = new File([""], "export", {
      type: "application/vnd.ms-excel.sheet.binary.macroEnabled.12",
    });
    expect(detectKind(file)).toBe("excel");
  });

  it("does not widen to unrelated types", () => {
    expect(detectKind(new File([""], "notes.txt", { type: "text/plain" }))).toBe("other");
    expect(detectKind(new File([""], "report.pdf", { type: "application/pdf" }))).toBe("pdf");
    expect(detectKind(new File([""], "rows.csv", { type: "text/csv" }))).toBe("csv");
  });
});
