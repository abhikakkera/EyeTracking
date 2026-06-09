import { describe, it, expect } from "vitest";
import {
  formatMilliseconds,
  formatPercent,
  formatCount,
  formatGain,
  formatMsDelta,
  formatPx,
  formatSpeed,
} from "../format";

describe("formatMilliseconds", () => {
  it("null / undefined / NaN => N/A", () => {
    expect(formatMilliseconds(null)).toBe("N/A");
    expect(formatMilliseconds(undefined)).toBe("N/A");
    expect(formatMilliseconds(Number.NaN)).toBe("N/A");
  });
  it("0 ms or negative is impossible for a response => N/A", () => {
    expect(formatMilliseconds(0)).toBe("N/A");
    expect(formatMilliseconds(-5)).toBe("N/A");
  });
  it("real value", () => {
    expect(formatMilliseconds(284)).toBe("284 ms");
    expect(formatMilliseconds(284.6)).toBe("285 ms");
  });
});

describe("formatPercent", () => {
  it("null => N/A", () => expect(formatPercent(null)).toBe("N/A"));
  it("genuine 0 => 0%", () => expect(formatPercent(0)).toBe("0%"));
  it("value", () => expect(formatPercent(87.5)).toBe("87.5%"));
});

describe("formatCount", () => {
  it("null => N/A", () => expect(formatCount(null)).toBe("N/A"));
  it("genuine 0 => 0", () => expect(formatCount(0)).toBe("0"));
  it("value", () => expect(formatCount(12)).toBe("12"));
});

describe("formatGain", () => {
  it("null => N/A", () => expect(formatGain(null)).toBe("N/A"));
  it("value", () => expect(formatGain(0.912)).toBe("0.91"));
});

describe("formatMsDelta (signed; 0 is valid)", () => {
  it("zero is a real value", () => expect(formatMsDelta(0)).toBe("0 ms"));
  it("negative", () => expect(formatMsDelta(-30)).toBe("-30 ms"));
  it("positive gets a sign", () => expect(formatMsDelta(45)).toBe("+45 ms"));
  it("null => N/A", () => expect(formatMsDelta(null)).toBe("N/A"));
});

describe("formatPx / formatSpeed", () => {
  it("null => N/A", () => {
    expect(formatPx(null)).toBe("N/A");
    expect(formatSpeed(undefined)).toBe("N/A");
  });
  it("values", () => {
    expect(formatPx(42.4)).toBe("42 px");
    expect(formatSpeed(420)).toBe("420 px/s");
  });
});
