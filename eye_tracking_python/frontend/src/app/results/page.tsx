"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import type { SessionSummary } from "@/lib/types";
import ResultsSummary from "@/components/ResultsSummary";

export default function LatestResultPage() {
  const { user, loading: authLoading } = useRequireAuth();
  const [summary, setSummary] = useState<SessionSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    let active = true;
    (async () => {
      try {
        const s = await api.latestResult();
        if (active) setSummary(s);
      } catch (e) {
        if (active)
          setError(
            e instanceof ApiError && e.status === 404
              ? "No completed sessions yet."
              : "Could not load your latest results.",
          );
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [user]);

  if (authLoading || !user || loading) {
    return (
      <section className="section">
        <div className="container">
          <p className="muted">Loading latest results…</p>
        </div>
      </section>
    );
  }

  if (error || !summary) {
    return (
      <section className="section">
        <div className="container">
          <div className="card center" style={{ maxWidth: 540, margin: "0 auto" }}>
            <h2>No results yet</h2>
            <p className="muted">{error}</p>
            <Link className="btn btn-primary" href="/test">
              Start an activity
            </Link>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="section">
      <div className="container" style={{ maxWidth: 900 }}>
        <ResultsSummary s={summary} />
        <div className="row mt-3">
          <Link
            className="btn btn-secondary"
            href={`/results/${summary.session_id}`}
          >
            View detailed results &amp; exports
          </Link>
          <Link className="btn btn-ghost" href="/history">
            Session history
          </Link>
        </div>
      </div>
    </section>
  );
}
