"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface UseWebcam {
  videoRef: React.RefObject<HTMLVideoElement>;
  ready: boolean;
  error: string | null;
  start: () => Promise<void>;
  stop: () => void;
}

/**
 * Manage a browser webcam stream via getUserMedia.
 * The same <video> element is reused for preview and for frame capture.
 */
export function useWebcam(autoStart = true): UseWebcam {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = useCallback(async () => {
    if (streamRef.current) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => {});
      }
      setReady(true);
      setError(null);
    } catch {
      setError(
        "Please allow camera access to start the eye movement activity.",
      );
      setReady(false);
    }
  }, []);

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setReady(false);
  }, []);

  useEffect(() => {
    if (autoStart) start();
    return () => stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { videoRef, ready, error, start, stop };
}
