"use client";

import { useEffect, useRef, useState } from "react";

type Check = "ok" | "pending";

/**
 * Camera setup preview.
 *
 * The browser preview is a framing/lighting aid only. When the user starts the
 * activity we RELEASE the browser camera so the Python tracker can take over —
 * the precise distance guidance happens live inside the activity window.
 */
export default function CameraSetupPanel({
  onStart,
  onBack,
  starting = false,
}: {
  onStart: () => void;
  onBack: () => void;
  starting?: boolean;
}) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [cameraOk, setCameraOk] = useState<Check>("pending");
  const [lighting, setLighting] = useState<Check>("pending");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let interval: ReturnType<typeof setInterval> | null = null;

    async function init() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { width: 640, height: 480, facingMode: "user" },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => {});
        }
        setCameraOk("ok");
        interval = setInterval(sampleBrightness, 800);
      } catch {
        setError(
          "We couldn't access your camera. Please allow camera access, or use “Start anyway”.",
        );
        setCameraOk("pending");
      }
    }

    function sampleBrightness() {
      const v = videoRef.current;
      if (!v || v.readyState < 2) return;
      const canvas = document.createElement("canvas");
      const w = (canvas.width = 64);
      const h = (canvas.height = 48);
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.drawImage(v, 0, 0, w, h);
      const { data } = ctx.getImageData(0, 0, w, h);
      let sum = 0;
      for (let i = 0; i < data.length; i += 4) {
        sum += 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
      }
      const mean = sum / (data.length / 4);
      setLighting(mean > 60 ? "ok" : "pending");
    }

    init();
    return () => {
      cancelled = true;
      if (interval) clearInterval(interval);
      releaseCamera();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function releaseCamera() {
    const s = streamRef.current;
    if (s) {
      s.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }

  function handleStart() {
    // Release the browser camera FIRST so the tracker can open it.
    releaseCamera();
    onStart();
  }

  const checks: { key: string; label: string; state: Check; hint: string }[] = [
    {
      key: "cam",
      label: "Camera connected",
      state: cameraOk,
      hint: cameraOk === "ok" ? "Great — your camera is on." : "Waiting for camera…",
    },
    {
      key: "light",
      label: "Lighting",
      state: lighting,
      hint:
        lighting === "ok"
          ? "Lighting looks good."
          : "Try adding more light on your face.",
    },
  ];

  return (
    <div className="grid grid-2" style={{ alignItems: "start" }}>
      <div className="cam-preview">
        {error ? (
          <div className="cam-placeholder">{error}</div>
        ) : (
          <video ref={videoRef} playsInline muted />
        )}
      </div>

      <div className="grid" style={{ gap: 18 }}>
        <div>
          <h3 style={{ marginBottom: 6 }}>Quick camera check</h3>
          <p className="muted" style={{ marginBottom: 0 }}>
            Sit about an arm&apos;s length away, face the camera, and keep your
            head centered. The activity window will guide your distance in real
            time.
          </p>
        </div>

        <ul className="checklist">
          {checks.map((c) => (
            <li key={c.key}>
              <span className={`tick ${c.state === "ok" ? "ok" : "pending"}`}>
                {c.state === "ok" ? "✓" : "•"}
              </span>
              <div>
                <strong style={{ display: "block", fontSize: ".95rem" }}>
                  {c.label}
                </strong>
                <span className="small muted">{c.hint}</span>
              </div>
            </li>
          ))}
        </ul>

        <div className="note small">
          Tips: “Move a little closer,” “Move a little farther back,” “Center
          your face,” and “Hold still for a moment” will appear inside the
          activity window while it runs.
        </div>

        <div className="row">
          <button
            className="btn btn-primary"
            onClick={handleStart}
            disabled={starting || cameraOk !== "ok"}
          >
            {starting ? "Starting…" : "Start activity"}
          </button>
          <button
            className="btn btn-secondary"
            onClick={handleStart}
            disabled={starting}
          >
            Start anyway
          </button>
          <button className="btn btn-ghost" onClick={onBack} disabled={starting}>
            Back
          </button>
        </div>
      </div>
    </div>
  );
}
