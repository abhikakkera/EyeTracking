"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import { activityBySlug } from "@/lib/constants";
import { DEFAULT_TASK_CONFIG } from "@/lib/taskConfigs";
import type { TaskType, WebConfig, WebEvent, TaskFrameContext, RecordingPhase } from "@/lib/types";

import { useWebcam } from "@/hooks/useWebcam";
import { useTrackingStream } from "@/hooks/useTrackingStream";
import { useFrameCapture } from "@/hooks/useFrameCapture";
import { useTaskRunner } from "@/hooks/useTaskRunner";
import { useStabilization } from "@/hooks/useStabilization";

import WebcamPreview from "@/components/WebcamPreview";
import CameraSetupGuide, { type GuideItem } from "@/components/CameraSetupGuide";
import TaskCanvas from "@/components/TaskCanvas";
import TaskInstructions from "@/components/TaskInstructions";
import TaskProgress from "@/components/TaskProgress";
import LiveTrackingStatus from "@/components/LiveTrackingStatus";
import DisclaimerBox from "@/components/DisclaimerBox";

type Phase = "setup" | "countdown" | "running" | "completing" | "error";

const WAITING_CTX: TaskFrameContext = {
  trial_id: "", trial_number: -1, task_phase: "waiting", target_visible: false,
  target_x: 0.5, target_y: 0.5, target_direction: "none", condition: "none",
  fixation_visible: false,
};

export default function RunPage({ params }: { params: { taskType: string } }) {
  const router = useRouter();
  const activity = activityBySlug(params.taskType);
  const taskType = params.taskType as TaskType;
  const { user } = useRequireAuth();

  const { videoRef, stream, ready, error: camError } = useWebcam(true);
  const tracking = useTrackingStream();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const [phase, setPhase] = useState<Phase>("setup");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [count, setCount] = useState(3);
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [debug, setDebug] = useState(false);
  const [faceLost, setFaceLost] = useState(false);

  const sessionStartMs = useRef(0);
  const webCfg = useRef<WebConfig | null>(null);
  const startedSession = useRef(false);
  const lastFaceMs = useRef(0);

  // Pre-task stabilization gate — require a steady tracking window before start.
  const stab = useStabilization(tracking.latest, {
    windowMs: webCfg.current?.stabilization_window_ms,
    minUsableRatio: webCfg.current?.stabilization_min_usable_ratio,
    minSamples: webCfg.current?.stabilization_min_samples,
  });

  // ---- Task runner ----
  const handleEvent = useCallback(
    (ev: WebEvent) => {
      if (sessionId) api.sendEvent(sessionId, ev).catch(() => {});
    },
    [sessionId],
  );

  const handleComplete = useCallback(async () => {
    setPhase("completing");
    try {
      if (sessionId) {
        await api.completeWebSession(sessionId);
        router.push(`/results/${sessionId}`);
      }
    } catch {
      setPhase("error");
      setErrorMsg("We couldn't finalize your results. Your data may still be saved — check History.");
    }
  }, [sessionId, router]);

  const runner = useTaskRunner({
    taskType,
    canvasRef,
    onEvent: handleEvent,
    onComplete: handleComplete,
  });

  // Stable handle to the runner. The runner object identity changes on every
  // render (and frame uploads re-render ~12×/s), so effects must NOT depend on
  // it directly or their timers get reset constantly.
  const runnerRef = useRef(runner);
  runnerRef.current = runner;

  // ---- Start the web session once the camera is live (and user is known) ----
  useEffect(() => {
    if (!activity || !ready || !user || startedSession.current) return;
    startedSession.current = true;
    (async () => {
      try {
        webCfg.current = await api.webConfig().catch(() => null);
        const res = await api.startWebSession({
          task_type: taskType,
          screen_width: typeof window !== "undefined" ? window.innerWidth : 1280,
          screen_height: typeof window !== "undefined" ? window.innerHeight : 720,
          task_config: DEFAULT_TASK_CONFIG[taskType] as unknown as Record<string, unknown>,
        });
        sessionStartMs.current = performance.now();
        setSessionId(res.session_id);
      } catch {
        setPhase("error");
        setErrorMsg("Could not reach the Ocula backend. Make sure it's running on port 8000.");
      }
    })();
  }, [activity, ready, taskType, user]);

  // ---- Frame streaming (setup → countdown → running) ----
  // Every frame is tagged with a recording_phase so the backend counts ONLY
  // "task" frames toward usable% / trial quality (setup & countdown excluded).
  const taggedContext = useCallback((): TaskFrameContext => {
    if (phase === "running") {
      const c = runner.getContext();
      const tp = c.task_phase;
      const rp: RecordingPhase =
        tp === "iti" ? "between_trials" : tp === "done" ? "complete" : "task";
      return { ...c, recording_phase: rp };
    }
    const rp: RecordingPhase = phase === "countdown" ? "countdown" : "stabilization";
    return { ...WAITING_CTX, recording_phase: rp };
  }, [phase, runner]);

  useFrameCapture({
    videoRef,
    sessionId,
    enabled: phase === "setup" || phase === "countdown" || phase === "running",
    getContext: taggedContext,
    getTaskStartMs: () => sessionStartMs.current,
    fps: webCfg.current?.upload_fps ?? 12,
    jpegQuality: webCfg.current?.jpeg_quality ?? 70,
    maxWidth: webCfg.current?.max_width ?? 640,
    maxHeight: webCfg.current?.max_height ?? 480,
    timeoutMs: webCfg.current?.backend_timeout_ms ?? 4000,
    onResult: tracking.update,
    onUpload: tracking.noteUpload,
  });

  // ---- Countdown ----
  // Depends ONLY on phase+count. The runner is read via runnerRef so that the
  // frequent frame-driven re-renders don't keep resetting the 800ms timer
  // (which previously left the countdown stuck on "3").
  useEffect(() => {
    if (phase !== "countdown") return;
    if (count <= 0) {
      setPhase("running");
      runnerRef.current.start();
      return;
    }
    const t = setTimeout(() => setCount((c) => c - 1), 800);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, count]);

  function beginCountdown(override = false) {
    // "Start anyway" before the gate is satisfied → tag the session lower-confidence.
    if (override && sessionId) {
      api
        .sendEvent(sessionId, { type: "stabilization_overridden", timestamp_ms: performance.now() })
        .catch(() => {});
    }
    setCount(3);
    setPhase("countdown");
    containerRef.current?.requestFullscreen?.().catch(() => {});
  }

  // ---- Live face-loss warning during the task (goal 8) ----
  // Track the last time a face was seen; if it's been gone longer than the
  // configured threshold, surface a gentle "center your face" prompt.
  useEffect(() => {
    if (tracking.latest?.face_detected) {
      lastFaceMs.current = performance.now();
      if (faceLost) setFaceLost(false);
    }
  }, [tracking.latest, faceLost]);

  useEffect(() => {
    if (phase !== "running") {
      setFaceLost(false);
      return;
    }
    lastFaceMs.current = performance.now();
    const warnMs = webCfg.current?.task_face_loss_warn_ms ?? 1000;
    const id = setInterval(() => {
      if (performance.now() - lastFaceMs.current > warnMs) setFaceLost(true);
    }, 250);
    return () => clearInterval(id);
  }, [phase]);

  const exit = useCallback(async () => {
    runner.cancel();
    if (sessionId) await api.cancelWebSession(sessionId).catch(() => {});
    if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
    router.push("/test");
  }, [runner, sessionId, router]);

  // Keyboard quit (Esc)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && (phase === "running" || phase === "countdown")) exit();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [phase, exit]);

  // ---- Unknown task ----
  if (!activity) {
    return (
      <section className="section">
        <div className="container">
          <div className="card center" style={{ maxWidth: 520, margin: "0 auto" }}>
            <h2>Activity not found</h2>
            <Link className="btn btn-primary" href="/test">Choose an activity</Link>
          </div>
        </div>
      </section>
    );
  }

  // ---- Error ----
  if (phase === "error") {
    return (
      <section className="section">
        <div className="container">
          <div className="card" style={{ maxWidth: 560, margin: "0 auto" }}>
            <h2>Something went wrong</h2>
            <div className="error-box mb-3">{errorMsg}</div>
            <div className="row">
              <Link className="btn btn-primary" href={`/run/${taskType}`}>Try again</Link>
              <Link className="btn btn-ghost" href="/test">Back to activities</Link>
            </div>
          </div>
        </div>
      </section>
    );
  }

  const guideItems: GuideItem[] = [
    {
      key: "face",
      label: "Face visible",
      state: stab.checks.face,
      hint: stab.checks.face === "ok" ? "We can see your face." : "Center your face in the view.",
    },
    {
      key: "eyes",
      label: "Eyes clear",
      state: stab.checks.eyes,
      hint: stab.checks.eyes === "ok" ? "Your eyes are clear." : "Look toward the camera.",
    },
    {
      key: "distance",
      label: "Distance good",
      state: stab.checks.distance,
      hint:
        tracking.latest?.distance_status === "too_close"
          ? "Move a little farther back."
          : tracking.latest?.distance_status === "too_far"
            ? "Move a little closer."
            : "Nice — good distance from the camera.",
    },
    {
      key: "lighting",
      label: "Lighting good",
      state: stab.checks.lighting,
      hint: stab.checks.lighting === "ok" ? "Lighting looks good." : "Try adding more light.",
    },
    {
      key: "stability",
      label: "Holding steady",
      state: stab.checks.stability,
      hint: stab.checks.stability === "ok" ? "Steady — you're ready." : "Hold still for a moment…",
    },
  ];

  // The capture <video> stays mounted across setup → countdown → running so
  // useFrameCapture never loses its source mid-activity. It is hidden off-screen;
  // the setup preview displays the SAME stream in its own element.
  const captureVideo = (
    <video
      ref={videoRef}
      autoPlay
      muted
      playsInline
      aria-hidden
      style={{
        position: "fixed",
        left: -99999,
        top: 0,
        width: 2,
        height: 2,
        opacity: 0,
        pointerEvents: "none",
      }}
    />
  );

  return (
    <>
      {captureVideo}

      {phase === "setup" ? (
        // ---- Setup phase ----
        <section className="section">
          <div className="container" style={{ maxWidth: 980 }}>
            <span className="eyebrow">Get ready</span>
            <h1 style={{ fontSize: "2rem", marginBottom: 6 }}>{activity.name}</h1>
            <p className="muted">{activity.technical}</p>

            <div className="grid grid-2" style={{ alignItems: "start", marginTop: 12 }}>
              <div>
                <WebcamPreview stream={stream} error={camError} />
                <div style={{ marginTop: 12 }}>
                  <LiveTrackingStatus result={tracking.latest} />
                </div>
              </div>

              <div className="grid" style={{ gap: 18 }}>
                <TaskInstructions taskType={taskType} />
                <CameraSetupGuide items={guideItems} />
                <div className="note small">
                  Camera frames are processed locally by the Ocula backend in this
                  prototype. Raw video is not saved unless debug recording is
                  enabled.
                </div>
                <div className="row" style={{ alignItems: "center" }}>
                  <button
                    className="btn btn-primary btn-lg"
                    onClick={() => beginCountdown(false)}
                    disabled={!sessionId || !ready || !stab.ready}
                  >
                    {stab.ready ? "Start activity" : "Hold steady…"}
                  </button>
                  {sessionId && ready && !stab.ready && (
                    <button
                      className="btn btn-ghost btn-lg"
                      onClick={() => beginCountdown(true)}
                      title="Starts now even though tracking isn't fully steady. This session will be tagged lower-confidence."
                    >
                      Start anyway
                    </button>
                  )}
                  <Link className="btn btn-ghost btn-lg" href="/test">Back</Link>
                </div>
                <p className="small muted" style={{ marginTop: 2 }}>
                  {stab.ready
                    ? "Great — your eyes are clear. You can begin."
                    : stab.guidance}
                </p>
                <label className="small muted" style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <input type="checkbox" checked={debug} onChange={(e) => setDebug(e.target.checked)} />
                  Show technical details
                </label>
                {debug && <LiveTrackingStatus result={tracking.latest} debug uploadFps={tracking.uploadFps} />}
              </div>
            </div>

            <div className="mt-4">
              <DisclaimerBox compact />
            </div>
          </div>
        </section>
      ) : (
        // ---- Countdown / running / completing: full-screen activity overlay ----
        <div className="activity-overlay" ref={containerRef}>
          <TaskCanvas canvasRef={canvasRef}>
            {phase === "countdown" && (
              <div className="countdown">
                <div className="countdown-num">{count > 0 ? count : "Go"}</div>
                <TaskInstructions taskType={taskType} compact />
              </div>
            )}

            {phase === "completing" && (
              <div className="countdown">
                <div className="pulse"><div className="eye" /></div>
                <p className="muted">Saving your results…</p>
              </div>
            )}
          </TaskCanvas>

          {phase === "running" && faceLost && (
            <div className="face-lost-banner" role="status">
              Let’s get your face centered again — keep looking at the screen.
            </div>
          )}

          {(phase === "running" || phase === "countdown") && (
            <>
              <div className="activity-top">
                <TaskProgress current={runner.state.trialNumber} total={runner.state.totalRounds} />
                <button className="btn btn-ghost activity-exit" onClick={exit}>Exit</button>
              </div>
              <div className="activity-bottom">
                <LiveTrackingStatus
                  result={tracking.latest}
                  subtle
                  debug={debug}
                  uploadFps={tracking.uploadFps}
                />
              </div>
            </>
          )}
        </div>
      )}
    </>
  );
}
