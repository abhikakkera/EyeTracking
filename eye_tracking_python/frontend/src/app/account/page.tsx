"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAuth, useRequireAuth } from "@/lib/auth";
import type { SessionRow } from "@/lib/types";

function fmtDate(epoch?: number | null): string {
  if (!epoch) return "—";
  try {
    return new Date(epoch * 1000).toLocaleDateString(undefined, {
      month: "long",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return "—";
  }
}

export default function AccountPage() {
  const { user, loading } = useRequireAuth();
  const { logout, setUser } = useAuth();
  const router = useRouter();
  const [count, setCount] = useState<number | null>(null);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    setName(user.name);
    api
      .listSessions()
      .then((rows: SessionRow[]) => setCount(rows.filter((r) => r.status === "completed").length))
      .catch(() => setCount(0));
  }, [user]);

  if (loading || !user) {
    return (
      <section className="section">
        <div className="container">
          <p className="muted">Loading your account…</p>
        </div>
      </section>
    );
  }

  async function saveName() {
    try {
      const updated = await api.updateName(name.trim());
      setUser(updated);
      setEditing(false);
      setMsg("Name updated.");
    } catch {
      setMsg("Could not update your name.");
    }
  }

  function handleLogout() {
    logout();
    router.push("/");
  }

  return (
    <section className="section">
      <div className="container" style={{ maxWidth: 720 }}>
        <span className="eyebrow">Account</span>
        <h1 style={{ marginBottom: 28 }}>Your account</h1>

        {msg && <div className="note mb-3">{msg}</div>}

        <div className="card">
          <div className="metric-row">
            <span className="k">Name</span>
            <span className="v">
              {editing ? (
                <span className="row" style={{ alignItems: "center" }}>
                  <input
                    className="input"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    style={{ width: 200, padding: "8px 10px" }}
                  />
                  <button className="btn btn-primary" onClick={saveName} style={{ padding: "8px 16px" }}>
                    Save
                  </button>
                  <button className="btn-link" onClick={() => setEditing(false)}>
                    Cancel
                  </button>
                </span>
              ) : (
                <span className="row" style={{ alignItems: "center", gap: 12 }}>
                  {user.name || "—"}
                  <button className="btn-link" onClick={() => setEditing(true)}>
                    Edit
                  </button>
                </span>
              )}
            </span>
          </div>
          <div className="metric-row">
            <span className="k">Email</span>
            <span className="v">{user.email}</span>
          </div>
          <div className="metric-row">
            <span className="k">Account created</span>
            <span className="v">{fmtDate(user.created_at)}</span>
          </div>
          <div className="metric-row">
            <span className="k">Sessions completed</span>
            <span className="v">{count ?? "—"}</span>
          </div>
        </div>

        <div className="row mt-3">
          <button className="btn btn-ghost" onClick={handleLogout}>
            Log out
          </button>
        </div>

        <p className="small muted mt-3" style={{ maxWidth: "62ch" }}>
          Your account and sessions are stored locally on this computer. This is a
          research prototype — it makes no production-security or HIPAA-compliance
          claims.
        </p>
      </div>
    </section>
  );
}
