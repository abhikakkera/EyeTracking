"use client";

import { useCallback, useRef, useState } from "react";
import type { FrameResult } from "@/lib/types";

export interface UseTrackingStream {
  latest: FrameResult | null;
  uploadFps: number;
  update: (r: FrameResult) => void;
  noteUpload: () => void;
}

/**
 * Holds the latest live tracking result from the backend and a measured
 * frame-upload rate (for the optional debug overlay).
 */
export function useTrackingStream(): UseTrackingStream {
  const [latest, setLatest] = useState<FrameResult | null>(null);
  const [uploadFps, setUploadFps] = useState(0);
  const stamps = useRef<number[]>([]);

  const update = useCallback((r: FrameResult) => setLatest(r), []);

  const noteUpload = useCallback(() => {
    const now = performance.now();
    const arr = stamps.current;
    arr.push(now);
    while (arr.length && now - arr[0] > 1000) arr.shift();
    setUploadFps(arr.length);
  }, []);

  return { latest, uploadFps, update, noteUpload };
}
