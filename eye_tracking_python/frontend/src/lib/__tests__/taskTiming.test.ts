import { describe, it, expect } from "vitest";
import {
  clamp,
  mulberry32,
  pursuitTargetPosition,
  shuffle,
  uid,
} from "@/lib/taskTiming";

describe("taskTiming", () => {
  it("uid produces 8-char ids", () => {
    expect(uid()).toHaveLength(8);
    expect(uid(4)).toHaveLength(4);
  });

  it("mulberry32 is deterministic for a seed", () => {
    const a = mulberry32(42);
    const b = mulberry32(42);
    expect(a()).toBeCloseTo(b());
    expect(a()).toBeCloseTo(b());
  });

  it("shuffle preserves length and elements", () => {
    const arr = [1, 2, 3, 4, 5];
    const out = shuffle(arr, mulberry32(7));
    expect(out).toHaveLength(5);
    expect([...out].sort()).toEqual([1, 2, 3, 4, 5]);
  });

  it("clamp bounds values", () => {
    expect(clamp(5, 0, 1)).toBe(1);
    expect(clamp(-5, 0, 1)).toBe(0);
    expect(clamp(0.5, 0, 1)).toBe(0.5);
  });

  it("pursuit horizontal starts centered and moves right at quarter period", () => {
    const f = 0.25; // period = 4s
    const amp = 0.35;
    const p0 = pursuitTargetPosition("horizontal", 0, f, amp);
    expect(p0.x).toBeCloseTo(0.5, 5);
    expect(p0.y).toBeCloseTo(0.5, 5);

    const pQ = pursuitTargetPosition("horizontal", 1000, f, amp); // quarter period
    expect(pQ.x).toBeGreaterThan(0.6); // sin(pi/2)=1 → ~0.85 (clamped)
  });

  it("pursuit circular stays within bounds", () => {
    for (let t = 0; t < 5000; t += 250) {
      const p = pursuitTargetPosition("circular", t, 0.25, 0.4);
      expect(p.x).toBeGreaterThanOrEqual(0.05);
      expect(p.x).toBeLessThanOrEqual(0.95);
      expect(p.y).toBeGreaterThanOrEqual(0.05);
      expect(p.y).toBeLessThanOrEqual(0.95);
    }
  });
});
