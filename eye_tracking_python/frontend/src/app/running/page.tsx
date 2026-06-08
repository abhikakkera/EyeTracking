"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { activityBySlug } from "@/lib/constants";
import type { TaskType, TestStatus } from "@/lib/types";

type Phase = "starting" | "running" | "completed" | "failed" | "error";

function RunningInner() {
  const router = useRouter();
  const params = useSearchParams();
  const slug = (params.get("task") ?? "") as TaskType;
  const activity = activityBySlug(slug);

  const [phase, setPhase] = useState<Phase>("starting");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [message, setMessage] = useState<string>("");
  const startedRef = useRef(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Launch the tracker once on mount.
  useEffect(() => {
    if (!activity) {
      setPhase("error");
      setMessage("Unknown activity. Please choose one to begin.");
      return;
    }
    if (startedRef.current) return;
    startedRef.current = true;

    (async () => {
      try {
        const res = await api.startTest({
          task_type: slug,
          participant_id: "anonymous",
          mode: "guided",
        });
        setSessionId(res.session_id);
        setPhase("running");
        beginPolling(res.session_id);
      } catch (e) {
        const msg =
          e instanceof ApiError
            ? e.message
            : "Could not reach the PDEYE backend. Is it running on port 8000?";
        setPhase("error");
        setMessage(msg);
      }
    })();

    return () => stopPolling();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function beginPolling(sid: string) {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.getStatus(sid);
        handleStatus(s.status, sid);
      } catch {
        // transient — keep polling
      }
    }, 1500);
  }

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  function handleStatus(status: TestStatus, sid: string) {
    if (status === "completed") {
      stopPolling();
      setPhase("completed");
      setTimeout(() => router.push(`/results/${sid}`), 900);
    } else if (status === "failed") {
      stopPolling();
      setPhase("failed");
      setMessage(
        "The activity didn't finish cleanly. This is usually a camera or lighting issue — try again.",
      );
    } else if (status === "cancelled") {
      stopPolling();
      setPhase("failed");
      setMessage("The activity was stopped.");
    }
  }

  async function handleStop() {
    if (sessionId) {
      try {
        await api.stopTest(sessionId);
      } catch {
        /* ignore */
      }
    }
    stopPolling();
    router.push("/test");
  }

  const progress =
    phase === "starting" ? 25 : phase === "running" ? 66 : phase === "completed" ? 100 : 40;

  return (
    <section className="section">
      <div className="container">
        <div className="status-wrap">
          {(phase === "starting" || phase === "running" || phase === "completed") && (
            <>
              <div className="pulse" aria-hidden>
                <div className="eye" />
              </div>

              <span className="eyebrow">{activity?.name ?? "Activity"}</span>
              <h1 style={{ fontSize: "2rem" }}>
                {phase === "completed"
                  ? "All done — loading your results"
                  : "Your eye movement activity is running"}
              </h1>
              <p className="muted">
                {phase === "completed"
                  ? "Great work. We're preparing your summary now."
                  : "Follow the instructions in the activity window. When the activity ends, your results will appear here automatically."}
              </p>

              <div className="progress mt-3">
                <span style={{ width: `${progress}%` }} />
              </div>

              <div className="steps">
                <span className={`step ${phase === "starting" ? "active" : ""}`}>
                  <span className="n">1</span> Preparing
                </span>
                <span className={`step ${phase === "running" ? "active" : ""}`}>
                  <span className="n">2</span> Activity running
                </span>
                <span className={`step ${phase === "completed" ? "active" : ""}`}>
                  <span className="n">3</span> Results
                </span>
              </div>

              {phase !== "completed" && (
                <div className="mt-4">
                  <button className="btn btn-ghost" onClick={handleStop}>
                    Stop activity
                  </button>
                </div>
              )}
            </>
          )}

          {(phase === "failed" || phase === "error") && (
            <div className="card" style={{ textAlign: "left" }}>
              <h2 style={{ marginBottom: 8 }}>
                {phase === "error" ? "Couldn't start the activity" : "Activity didn't finish"}
              </h2>
              <div className="error-box mb-3">{message}</div>
              <div className="row">
                <Link className="btn btn-primary" href={`/setup?task=${slug}`}>
                  Try again
                </Link>
                <Link className="btn btn-ghost" href="/test">
                  Back to activities
                </Link>
              </div>
              <p className="small muted mt-3" style={{ marginBottom: 0 }}>
                Tip: make sure the backend is running with{" "}
                <code>python3 backend/app.py</code> and that no other app is using
                your camera.
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

export default function RunningPage() {
  return (
    <Suspense
      fallback={
        <section className="section">
          <div className="container">
            <p className="muted">Preparing…</p>
          </div>
        </section>
      }
    >
      <RunningInner />
    </Suspense>
  );
}
