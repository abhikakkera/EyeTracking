"use client";

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import TaskInstructions from "@/components/TaskInstructions";
import DisclaimerBox from "@/components/DisclaimerBox";
import { activityBySlug } from "@/lib/constants";
import type { TaskType } from "@/lib/types";

function SetupInner() {
  const router = useRouter();
  const params = useSearchParams();
  const slug = params.get("task") ?? "";
  const activity = activityBySlug(slug);

  if (!activity) {
    return (
      <section className="section">
        <div className="container">
          <div className="card center" style={{ maxWidth: 520, margin: "0 auto" }}>
            <h2>Activity not found</h2>
            <p className="muted">Please choose an activity to continue.</p>
            <Link className="btn btn-primary" href="/test">Choose an activity</Link>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="section">
      <div className="container" style={{ maxWidth: 760 }}>
        <span className="eyebrow">Before you start</span>
        <h1 style={{ fontSize: "2.2rem", marginBottom: 6 }}>{activity.name}</h1>
        <p className="muted">{activity.technical} · {activity.duration}</p>

        <div className="card mt-3">
          <TaskInstructions taskType={slug as TaskType} />
        </div>

        <div className="card mt-3">
          <h3 className="mb-2">What to expect</h3>
          <ul className="checklist">
            <li><span className="tick ok">①</span><span>The next screen runs the activity <strong>inside this website</strong> — no separate window.</span></li>
            <li><span className="tick ok">②</span><span>We&apos;ll ask for camera access and show a quick live setup check.</span></li>
            <li><span className="tick ok">③</span><span>Blue dots appear on a clean full-screen canvas. Follow the instructions.</span></li>
            <li><span className="tick ok">④</span><span>Your results appear automatically when you finish.</span></li>
          </ul>
          <div className="note small mt-2">
            Camera frames are processed locally by the PDEYE backend in this
            prototype. Raw video is not saved unless debug recording is enabled.
          </div>
        </div>

        <div className="row mt-3">
          <button
            className="btn btn-primary btn-lg"
            onClick={() => router.push(`/run/${activity.slug}`)}
          >
            Continue to camera check
          </button>
          <Link className="btn btn-ghost btn-lg" href="/test">Back</Link>
        </div>

        <div className="mt-4">
          <DisclaimerBox compact />
        </div>
      </div>
    </section>
  );
}

export default function SetupPage() {
  return (
    <Suspense
      fallback={
        <section className="section">
          <div className="container">
            <p className="muted">Loading…</p>
          </div>
        </section>
      }
    >
      <SetupInner />
    </Suspense>
  );
}
