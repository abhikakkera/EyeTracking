"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { SessionRow } from "@/lib/types";
import SessionTable from "@/components/SessionTable";
import DisclaimerBox from "@/components/DisclaimerBox";

export default function HistoryPage() {
  const [rows, setRows] = useState<SessionRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listSessions(100);
      setRows(data);
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : "Could not reach the backend. Is it running on port 8000?",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function openFolder() {
    try {
      await api.openFolder();
    } catch {
      /* ignore */
    }
  }

  return (
    <section className="section">
      <div className="container">
        <div className="row-between" style={{ marginBottom: 28 }}>
          <div>
            <span className="eyebrow">Your data</span>
            <h1 style={{ fontSize: "2.2rem", marginBottom: 4 }}>
              Previous Sessions
            </h1>
            <p className="muted" style={{ marginBottom: 0 }}>
              Every completed activity is saved locally on this computer.
            </p>
          </div>
          <div className="row">
            <button className="btn btn-ghost" onClick={load} disabled={loading}>
              {loading ? "Refreshing…" : "Refresh"}
            </button>
            <button className="btn btn-secondary" onClick={openFolder}>
              Open results folder
            </button>
          </div>
        </div>

        {error ? (
          <div className="error-box mb-3">{error}</div>
        ) : (
          <SessionTable rows={rows} />
        )}

        <div className="mt-4">
          <DisclaimerBox compact />
        </div>
      </div>
    </section>
  );
}
