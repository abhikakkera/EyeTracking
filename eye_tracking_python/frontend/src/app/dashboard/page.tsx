"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import type { SessionRow } from "@/lib/types";
import QualityBadge from "@/components/QualityBadge";
import { formatPercent } from "@/lib/format";

function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return "—";
  }
}

export default function DashboardPage() {
  const { user, loading } = useRequireAuth();
  const [rows, setRows] = useState<SessionRow[] | null>(null);

  useEffect(() => {
    if (!user) return;
    api.listSessions().then(setRows).catch(() => setRows([]));
  }, [user]);

  if (loading || !user) {
    return (
      <section className="section">
        <div className="container">
          <p className="muted">Loading your dashboard…</p>
        </div>
      </section>
    );
  }

  const completed = (rows || []).filter((r) => r.status === "completed");
  const latest = completed[0];
  const firstName = user.name?.split(" ")[0] || "there";

  return (
    <section className="section">
      <div className="container">
        <div className="welcome">
          <div>
            <span className="eyebrow">Dashboard</span>
            <h1>Welcome back, {firstName}.</h1>
          </div>
          <Link className="btn btn-primary btn-lg" href="/test">
            Start a new session
          </Link>
        </div>

        {/* Top cards */}
        <div className="dash-grid">
          <div className="dash-cta">
            <div>
              <h3>Run a short activity</h3>
              <p>Pick a dot-following activity and follow along. It takes a couple of minutes.</p>
            </div>
            <Link className="btn" href="/test">
              Choose an activity →
            </Link>
          </div>

          <div className="dash-metric">
            <div className="k">Sessions completed</div>
            <div className="v">{completed.length}</div>
            <div className="sub">{completed.length === 0 ? "None yet" : "Saved to your account"}</div>
          </div>

          <div className="dash-metric">
            <div className="k">Latest tracking quality</div>
            <div className="v" style={{ fontSize: "1.2rem", marginTop: 4 }}>
              {latest ? <QualityBadge label={latest.tracking_quality_label} /> : "—"}
            </div>
            <div className="sub">
              {latest ? `Most recent: ${latest.activity_name ?? "—"}` : "Run a session to see this"}
            </div>
          </div>
        </div>

        {/* History */}
        <div className="row-between mt-5 mb-2">
          <h2 style={{ margin: 0 }}>Your sessions</h2>
          {completed.length > 0 && (
            <Link className="btn-link" href="/history">
              View all →
            </Link>
          )}
        </div>

        {rows === null ? (
          <p className="muted">Loading sessions…</p>
        ) : completed.length === 0 ? (
          <div className="empty-state">
            <h3>You have not completed a session yet.</h3>
            <p>Start with a short dot-following activity — your results will appear here.</p>
            <Link className="btn btn-primary" href="/test">
              Start your first session
            </Link>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Activity</th>
                  <th>Tracking quality</th>
                  <th>Usable data</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {completed.slice(0, 6).map((r) => (
                  <tr key={r.session_id}>
                    <td>{fmtDate(r.date_time)}</td>
                    <td>{r.activity_name ?? r.task_type}</td>
                    <td>
                      <QualityBadge label={r.tracking_quality_label} />
                    </td>
                    <td>{formatPercent(r.usable_data_percent)}</td>
                    <td style={{ textAlign: "right" }}>
                      <Link className="btn-link" href={`/results/${r.session_id}`}>
                        View results →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
