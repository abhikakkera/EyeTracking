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
 */
export function useFrameCapture(opts: FrameCaptureOptions): void {
  const inFlight = useRef(false);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const {
      videoRef, sessionId, enabled, getContext, getTaskStartMs,
      fps = 12, jpegQuality = 70, maxWidth = 640, maxHeight = 480,
      timeoutMs = 4000, onResult, onUpload, onSlow,
    } = opts;

    if (!enabled || !sessionId) return;

    if (!canvasRef.current) canvasRef.current = document.createElement("canvas");
    const intervalMs = 1000 / Math.max(1, fps);
    let stopped = false;

    async function captureOnce() {
      if (stopped || inFlight.current) return;
      const video = videoRef.current;
      const canvas = canvasRef.current;
      if (!video || !canvas || video.readyState < 2) return;

      // Compute capped output size, preserving aspect ratio.
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

      const blob: Blob | null = await new Promise((resolve) =>
        canvas.toBlob((b) => resolve(b), "image/jpeg", jpegQuality / 100),
      );
      if (!blob || stopped) return;

      const meta = {
        ...getContext(),
        browser_timestamp_ms: performance.now(),
        task_start_timestamp_ms: getTaskStartMs(),
      };

      inFlight.current = true;
      try {
        const result = await api.sendFrame(sessionId!, blob, meta, timeoutMs);
        onUpload?.();
        onResult?.(result);
      } catch {
        onSlow?.();
      } finally {
        inFlight.current = false;
      }
    }

    const timer = setInterval(captureOnce, intervalMs);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opts.sessionId, opts.enabled, opts.fps]);
}
