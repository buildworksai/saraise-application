import type { DecimalString } from "./contracts";

/** Add fixed four-decimal monetary strings without IEEE-754 rounding. */
export function fixedAdd(values: readonly DecimalString[]): DecimalString {
  const scale = 10_000n;
  const total = values.reduce((sum, value) => {
    const negative = value.trim().startsWith("-");
    const [whole = "0", fraction = ""] = value.replace("-", "").split(".");
    const units = BigInt(whole || "0") * scale + BigInt(`${fraction}0000`.slice(0, 4));
    return sum + (negative ? -units : units);
  }, 0n);
  const sign = total < 0n ? "-" : "";
  const absolute = total < 0n ? -total : total;
  return `${sign}${absolute / scale}.${String(absolute % scale).padStart(4, "0")}`;
}
