// Pure timing + geometry helpers for the in-browser task runner.
// Kept dependency-free and side-effect-free so they can be unit-tested.

export function nowMs(): number {
  // performance.now() is monotonic and high-resolution; fall back to Date.
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}

export function uid(n = 8): string {
  // Short, collision-unlikely id without external deps.
  return Math.random().toString(16).slice(2, 2 + n).padEnd(n, "0");
}

// Deterministic RNG (mulberry32) for reproducible trial shuffles in tests.
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function shuffle<T>(arr: T[], rng: () => number = Math.random): T[] {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

export function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

export type PursuitPattern = "horizontal" | "vertical" | "circular" | "figure8";

/**
 * Normalized [0,1] target position for the smooth-pursuit dot at a given
 * elapsed time. Mirrors the Python SmoothPursuitTask paths so reconstructed
 * metrics are comparable.
 */
export function pursuitTargetPosition(
  pattern: PursuitPattern,
  elapsedMs: number,
  cyclesPerSec: number,
  amplitude: number,
  cx = 0.5,
  cy = 0.5,
): { x: number; y: number } {
  const phase = 2 * Math.PI * cyclesPerSec * (elapsedMs / 1000);
  let x = cx;
  let y = cy;
  switch (pattern) {
    case "vertical":
      y = cy + amplitude * Math.sin(phase);
      break;
    case "circular":
      x = cx + amplitude * Math.cos(phase);
      y = cy + amplitude * Math.sin(phase);
      break;
    case "figure8":
      x = cx + amplitude * Math.sin(phase);
      y = cy + (amplitude / 2) * Math.sin(2 * phase);
      break;
    case "horizontal":
    default:
      x = cx + amplitude * Math.sin(phase);
      break;
  }
  const m = 0.05;
  return { x: clamp(x, m, 1 - m), y: clamp(y, m, 1 - m) };
}
