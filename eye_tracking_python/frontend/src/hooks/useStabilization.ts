"use client";

import { useEffect, useRef, useState } from "react";
import type { FrameResult } from "@/lib/types";

export type CheckState = "ok" | "warn" | "pending";

export interface StabilizationChecks {
  face: CheckState;
  eyes: CheckState;
  distance: CheckState;
  lighting: CheckState;
  stability: CheckState;
}

export interface Stabilization {
  ready: boolean;
  checks: StabilizationChecks;
  usableRatio: number;
  samples: number;
  guidance: string;
}

interface Sample {
  t: number;
  face: boolean;
  eyes: boolean;
  usable: boolean;
  distanceOk: boolean;
  lightOk: boolean;
}

const EMPTY: Stabilization = {
  ready: false,
  checks: { face: "pending", eyes: "pending", distance: "pending", lighting: "pending", stability: "pending" },
  usableRatio: 0,
  samples: 0,
  guidance: "Waiting for the camera…",
};

/**
 * Requires a short STABLE tracking window before the task may start.
 *
 * Consumes the live FrameResult stream and keeps a rolling window of the last
 * `windowMs`. Reports per-check status (face / eyes / distance / lighting /
 * stability) and an overall `ready` flag once the window is full and ≥
 * `minUsableRatio` of recent frames were usable.
 *
 * Friendly, non-clinical guidance only.
 */
export function useStabilization(
  result: FrameResult | null,
  opts: { windowMs?: number; minUsableRatio?: number; minSamples?: number } = {},
): Stabilization {
  const windowMs = opts.windowMs ?? 1500;
  const minUsableRatio = opts.minUsableRatio ?? 0.8;
  const minSamples = opts.minSamples ?? 8;

  const buf = useRef<Sample[]>([]);
  const [state, setState] = useState<Stabilization>(EMPTY);

  useEffect(() => {
    if (!result) return;
    const now = performance.now();

    const face = !!result.face_detected;
    const eyes = face && (result.confidence ?? 0) > 0.1;
    const distanceOk = result.distance_status === "good" || result.distance_status === "unknown";
    const msg = (result.guidance_message || "").toLowerCase();
    const lightOk = !msg.includes("light") && !msg.includes("bright");
    const usable = face && eyes && result.tracking_status !== "bad";

    const arr = buf.current;
    arr.push({ t: now, face, eyes, usable, distanceOk, lightOk });
    while (arr.length && now - arr[0].t > windowMs) arr.shift();

    const n = arr.length;
    const ratio = n ? arr.filter((s) => s.usable).length / n : 0;
    const faceRatio = n ? arr.filter((s) => s.face).length / n : 0;
    const distRatio = n ? arr.filter((s) => s.distanceOk).length / n : 0;
    const lightRatio = n ? arr.filter((s) => s.lightOk).length / n : 0;
    const windowFull = n >= minSamples && now - arr[0].t >= windowMs * 0.8;

    const cs = (v: boolean, pending: boolean): CheckState =>
      pending ? "pending" : v ? "ok" : "warn";

    const checks: StabilizationChecks = {
      face: cs(faceRatio >= 0.8, n < 3),
      eyes: cs(face && eyes, n < 3),
      distance: cs(distRatio >= 0.8, n < 3),
      lighting: cs(lightRatio >= 0.8, n < 3),
      stability: cs(windowFull && ratio >= minUsableRatio, !windowFull),
    };

    const ready =
      windowFull &&
      ratio >= minUsableRatio &&
      checks.face === "ok" &&
      checks.distance === "ok";

    let guidance = "Hold still for a moment…";
    if (!face) guidance = "Center your face in the view.";
    else if (result.distance_status === "too_close") guidance = "Move a little farther back.";
    else if (result.distance_status === "too_far") guidance = "Move a little closer.";
    else if (!lightOk) guidance = "Try adding more light.";
    else if (!windowFull) guidance = "Hold still for a moment…";
    else if (ready) guidance = "Great — your eyes are clear.";
    else guidance = "Almost there — keep your head steady.";

    setState({ ready, checks, usableRatio: ratio, samples: n, guidance });
  }, [result, windowMs, minUsableRatio, minSamples]);

  return state;
}
