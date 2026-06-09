// Null-safe display formatters for PDEYE results.
//
// Rule: null / undefined / NaN  =>  "N/A".
// A value displays as 0 only when it is a genuine numeric 0 (e.g. "0 rounds").
// Reaction times are special: a response time of 0 ms is physically impossible,
// so 0 (or negative) is treated as missing → "N/A".

export const NA = "N/A";

export function isNum(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

/** Generic number — null/NaN => "N/A". 0 is shown. */
export function formatNumber(v: unknown, digits = 0): string {
  if (!isNum(v)) return NA;
  return digits > 0 ? v.toFixed(digits) : String(Math.round(v));
}

/** Integer count — null/NaN => "N/A". 0 is shown (it's a real count). */
export function formatCount(v: unknown): string {
  if (!isNum(v)) return NA;
  return String(Math.round(v));
}

/** Percent (value already 0–100) — null/NaN => "N/A". 0% is shown. */
export function formatPercent(v: unknown): string {
  if (!isNum(v)) return NA;
  return `${Math.round(v * 10) / 10}%`;
}

/**
 * Reaction time in ms — null/NaN => "N/A".
 * 0 ms (or negative) is impossible for a real response → treated as missing.
 */
export function formatMilliseconds(v: unknown): string {
  if (!isNum(v) || v <= 0) return NA;
  return `${Math.round(v)} ms`;
}

/** A signed millisecond delta (e.g. gap effect) — 0 and negatives are valid. */
export function formatMsDelta(v: unknown): string {
  if (!isNum(v)) return NA;
  const r = Math.round(v);
  return `${r > 0 ? "+" : ""}${r} ms`;
}

/** Pursuit gain or similar ratio — null/NaN => "N/A". */
export function formatGain(v: unknown): string {
  if (!isNum(v)) return NA;
  return v.toFixed(2);
}

/** Pixel distance — null/NaN => "N/A". */
export function formatPx(v: unknown): string {
  if (!isNum(v)) return NA;
  return `${Math.round(v)} px`;
}

/** Pixels/second speed — null/NaN => "N/A". */
export function formatSpeed(v: unknown): string {
  if (!isNum(v)) return NA;
  return `${Math.round(v)} px/s`;
}

/** Confidence 0–1 — null/NaN => "N/A". */
export function formatConfidence(v: unknown): string {
  if (!isNum(v)) return NA;
  return v.toFixed(3);
}
