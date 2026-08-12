import type { DecimalString } from "./contracts";

/** Add fixed four-decimal monetary strings without IEEE-754 rounding. */
export function fixedAdd(values: readonly DecimalString[]): DecimalString {
  const scale = 10_000n;
  const total = values.reduce((sum, value) => {
    const normalized = value.trim();
    const negative = normalized.startsWith("-");
    const explicitPositive = normalized.startsWith("+");
    const unsigned = negative || explicitPositive ? normalized.slice(1) : normalized;
    const separatorIndex = unsigned.indexOf(".");
    const whole = separatorIndex === -1 ? unsigned : unsigned.slice(0, separatorIndex);
    const fraction = separatorIndex === -1 ? "" : unsigned.slice(separatorIndex + 1);
    const wholeUnits = BigInt(whole) * scale;
    const fractionalUnits = BigInt(`${fraction}0000`.slice(0, 4));
    const units = wholeUnits + fractionalUnits;
    return sum + (negative ? -units : units);
  }, 0n);
  const sign = total < 0n ? "-" : "";
  const absolute = sign === "-" ? -total : total;
  return `${sign}${absolute / scale}.${String(absolute % scale).padStart(4, "0")}`;
}
