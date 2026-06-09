"use client";

import { useEffect, useRef } from "react";
import { api } from "@/lib/api";
import type { FrameResult, TaskFrameContext } from "@/lib/types";

export interface FrameCaptureOptions {
  videoRef: React.RefObject<HTMLVideoElement>;
  sessionId: string | null;
  enabled: boolean;
  getContext: () => TaskFrameContext;
  getTaskStartMs: () => number;
  fps?: number;
  jpegQuality?: number;
  maxWidth?: number;
  maxHeight?: number;
  timeoutMs?: number;
  onResult?: (r: FrameResult) => void;
  onUpload?: () => void;
  onSlow?: () => void;
}

/**
 * Captures webcam frames at a target FPS and streams them to the backend.
 *
 * - Mirrors horizontally so screen-right == image-right (intuitive gaze).
 * - Backpressure: never more than one request in flight; ticks are dropped
 *   while the backend is busy (keeps the UI smooth — no freezing).
 * - JPEG compression + capped resolution to keep uploads small.
 *
 * IMPORTANT: the capture loop reads every option through a `latest` ref, so it
 * always uses the CURRENT getContext()/callbacks. Without this, the interval
 * would freeze the closure from the render when it started — which made every
 * frame get tagged with the "waiting" context even after the task began.
 */
export function useFrameCapture(opts: FrameCaptureOptions): void {
  const inFlight = useRef(false);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // Always-current snapshot of the options for the interval to read.
  const latest = useRef(opts);
  latest.current = opts;

  useEffect(() => {
    if (!opts.enabled || !opts.sessionId) return;

    if (!canvasRef.current) canvasRef.current = document.createElement("canvas");
    const intervalMs = 1000 / Math.max(1, opts.fps ?? 12);
    let stopped = false;

    async function captureOnce() {
      const o = latest.current;
      if (stopped || inFlight.current || !o.sessionId) return;

      const video = o.videoRef.current;
      const canvas = canvasRef.current;
      if (!video || !canvas || video.readyState < 2) return;

      const maxWidth = o.maxWidth ?? 640;
      const maxHeight = o.maxHeight ?? 480;
      const vw = video.videoWidth || maxWidth;
      const vh = video.videoHeight || maxHeight;
      const scale = Math.min(maxWidth / vw, maxHeight / vh, 1);
      const w = Math.round(vw * scale);
      const h = Math.round(vh * scale);
      canvas.width = w;
      canvas.height = h;

      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      // Mirror horizontally → screen space.
      ctx.save();
      ctx.translate(w, 0);
      ctx.scale(-1, 1);
      ctx.drawImage(video, 0, 0, w, h);
      ctx.restore();

      const quality = (o.jpegQuality ?? 70) / 100;
      const blob: Blob | null = await new Promise((resolve) =>
        canvas.toBlob((b) => resolve(b), "image/jpeg", quality),
      );
      if (!blob || stopped) return;

      const meta = {
        ...o.getContext(),
        browser_timestamp_ms: performance.now(),
        task_start_timestamp_ms: o.getTaskStartMs(),
      };

      inFlight.current = true;
      try {
        const result = await api.sendFrame(o.sessionId, blob, meta, o.timeoutMs ?? 4000);
        o.onUpload?.();
        o.onResult?.(result);
      } catch {
        o.onSlow?.();
      } finally {
        inFlight.current = false;
      }
    }

    const timer = setInterval(captureOnce, intervalMs);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
    // Re-create the loop only when these change; everything else is read live.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opts.sessionId, opts.enabled, opts.fps]);
}
