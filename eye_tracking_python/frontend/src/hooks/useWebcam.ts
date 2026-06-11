"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface UseWebcam {
  videoRef: React.RefObject<HTMLVideoElement>;
  stream: MediaStream | null;
  ready: boolean;
  error: string | null;
  start: () => Promise<void>;
  stop: () => void;
}

/**
 * Manage a browser webcam stream via getUserMedia.
 *
 * `videoRef` points at a single PERSISTENT capture <video> (kept mounted for
 * the whole activity so frame capture never loses its source). `stream` is also
 * exposed so the setup preview can display the same stream in its own element.
 */
export function useWebcam(autoStart = true): UseWebcam {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = useCallback(async () => {
    if (streamRef.current) return;
    try {
      // Request a higher-resolution stream so the backend gets sharper frames
      // (better face/eye detection). The capture loop still downscales to the
      // server's max_width/max_height before upload, so bandwidth stays bounded.
      const s = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
        audio: false,
      });
      streamRef.current = s;
      setStream(s);
      if (videoRef.current) {
        videoRef.current.srcObject = s;
        await videoRef.current.play().catch(() => {});
      }
      setReady(true);
      setError(null);
    } catch {
      setError("Please allow camera access to start the eye movement activity.");
      setReady(false);
    }
  }, []);

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setStream(null);
    setReady(false);
  }, []);

  // Keep the persistent capture video bound to the stream even if it (re)mounts.
  useEffect(() => {
    if (videoRef.current && streamRef.current) {
      videoRef.current.srcObject = streamRef.current;
      videoRef.current.play().catch(() => {});
    }
  });

  useEffect(() => {
    if (autoStart) start();
    return () => stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { videoRef, stream, ready, error, start, stop };
}
