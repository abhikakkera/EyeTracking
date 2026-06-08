import Link from "next/link";
import type { SessionRow } from "@/lib/types";
import QualityBadge from "@/components/QualityBadge";

function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function SessionTable({ rows }: { rows: SessionRow[] }) {
  if (!rows.length) {
    return (
      <div className="card center">
        <p className="muted" style={{ marginBottom: 16 }}>
          No sessions yet. Your completed activities will appear here.
        </p>
        <Link className="btn btn-primary" href="/test">
          Start your first activity
        </Link>
      </div>
    );
  }

  return (
    <div className="table-wrap">
      <table className="tbl">
        <thead>
          <tr>
            <th>Date</th>
            <th>Activity</th>
            <th>Tracking quality</th>
            <th>Rounds</th>
            <th>Usable data</th>
            <th aria-label="actions" />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.session_id}>
              <td>{fmtDate(r.date_time)}</td>
              <td>
                <strong>{r.activity_name || r.task_type}</strong>
              </td>
              <td>
                {r.status === "completed" ? (
                  <QualityBadge label={r.tracking_quality_label} />
                ) : (
                  <span className="badge badge-gray">{r.status}</span>
                )}
              </td>
              <td>{r.rounds_completed ?? "—"}</td>
              <td>
                {r.usable_data_percent != null
                  ? `${r.usable_data_percent}%`
                  : "—"}
              </td>
              <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                <Link
                  className="btn btn-ghost"
                  href={`/results/${r.session_id}`}
                  style={{ padding: "8px 14px" }}
                >
                  View
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
