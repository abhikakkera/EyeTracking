"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import type { SessionSummary } from "@/lib/types";
import ResultsSummary from "@/components/ResultsSummary";

const EXPORT_KINDS: { kind: string; label: string }[] = [
  { kind: "trials", label: "Trial data (CSV)" },
  { kind: "frames", label: "Frame data (CSV)" },
  { kind: "task_metadata", label: "Summary (JSON)" },
  { kind: "events", label: "Events (JSON)" },
];

export default function ResultDetailPage({
  params,
}: {
  params: { sessionId: string };
}) {
  const sid = params.sessionId;
  const [summary, setSummary] = useState<SessionSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [folderMsg, setFolderMsg] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const s = await api.getResult(sid);
        if (active) setSummary(s);
      } catch (e) {
        if (active)
          setError(
            e instanceof ApiError ? e.message : "Could not load this session.",
          );
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [sid]);

  async function openFolder() {
    try {
      const r = await api.openFolder();
      setFolderMsg(
        r.opened ? "Opened the results folder." : `Results are in: ${r.path}`,
      );
    } catch {
      setFolderMsg("Could not open the folder automatically.");
    }
  }

  if (loading) {
    return (
      <section className="section">
        <div className="container">
          <p className="muted">Loading results…</p>
        </div>
      </section>
    );
  }

  if (error || !summary) {
    return (
      <section className="section">
        <div className="container">
          <div className="card center" style={{ maxWidth: 520, margin: "0 auto" }}>
            <h2>Session not found</h2>
            <div className="error-box mb-3">{error ?? "No data available."}</div>
            <Link className="btn btn-primary" href="/history">
              Back to history
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

        {/* Export + actions */}
        <div className="card mt-3">
          <h3 className="mb-2">Export research data</h3>
          <p className="muted small">
            Files are stored locally on your computer. Download a copy or open the
            folder directly.
          </p>
          <div className="row" style={{ marginTop: 6 }}>
            {EXPORT_KINDS.map((e) =>
              summary.exports?.[e.kind] ? (
                <a
                  key={e.kind}
                  className="btn btn-secondary"
                  href={api.downloadUrl(sid, e.kind)}
                  target="_blank"
                  rel="noreferrer"
                >
                  ↓ {e.label}
                </a>
              ) : null,
            )}
            <button className="btn btn-ghost" onClick={openFolder}>
              Open results folder
            </button>
          </div>
          {folderMsg && <div className="note small mt-2">{folderMsg}</div>}
        </div>

        <div className="row mt-3">
          <Link className="btn btn-primary" href="/test">
            Start another activity
          </Link>
          <Link className="btn btn-ghost" href="/history">
            View session history
          </Link>
          <Link className="btn btn-ghost" href="/">
            Return home
          </Link>
        </div>
      </div>
    </section>
  );
}
