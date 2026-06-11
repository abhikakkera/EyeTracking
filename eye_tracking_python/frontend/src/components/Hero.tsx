"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth";
import DisclaimerBox from "@/components/DisclaimerBox";

export default function Hero() {
  const { user } = useAuth();
  const startHref = user ? "/test" : "/signup";

  return (
    <section className="hero">
      <div className="container hero-grid">
        <div className="fade-up">
          <span className="eyebrow">Ocula</span>
          <h1>Eye movement tracking, made simple.</h1>
          <p className="lead-xl">
            Ocula guides you through short visual activities and records eye
            movement patterns with your camera — designed for research-quality
            data collection, personal review, and future neurological research.
          </p>

          <div className="hero-actions">
            <Link className="btn btn-primary btn-lg" href={startHref}>
              Start a session
            </Link>
            <Link className="btn btn-ghost btn-lg" href="/about">
              Learn about Ocula
            </Link>
          </div>

          <div style={{ maxWidth: 540, marginTop: 22 }}>
            <DisclaimerBox
              compact
              text="Ocula is not a diagnostic tool. It does not diagnose, treat, predict, or screen for Parkinson's disease or any other condition."
            />
          </div>
        </div>

        <div className="hero-visual fade-up" aria-hidden>
          <div className="fix" />
          <div className="target" />
          <div className="gaze-dot" />
        </div>
      </div>
    </section>
  );
}
