import type { SessionSummary } from "@/lib/types";
import QualityBadge from "@/components/QualityBadge";
import DisclaimerBox from "@/components/DisclaimerBox";

// Friendly labels for known per-task metric keys.
const LABELS: Record<string, string> = {
  // pro-saccade
  average_response_time_ms: "Average response time",
  fastest_response_ms: "Fastest response",
  successful_clear_rounds: "Successful clear rounds",
  unclear_rounds: "Rounds with unclear tracking",
  direction_accuracy_percent: "Correct direction",
  left_accuracy_percent: "Accuracy (left targets)",
  right_accuracy_percent: "Accuracy (right targets)",
  response_rate_percent: "Rounds with a response",
  // anti-saccade
  correct_direction_rounds: "Correct-direction rounds",
  self_corrections: "Self-corrections",
  error_rate_percent: "Looked toward the dot first",
  correction_rate_percent: "Self-correction rate",
  // gap-overlap
  average_response_time_gap_ms: "Avg response — gap",
  average_response_time_overlap_ms: "Avg response — overlap",
  gap_effect_ms: "Gap effect",
  gap_valid_rounds: "Valid gap rounds",
  overlap_valid_rounds: "Valid overlap rounds",
  gap_trials: "Gap rounds",
  overlap_trials: "Overlap rounds",
  // smooth pursuit
  mean_pursuit_gain: "Tracking closeness (gain)",
  mean_position_error_px: "Average tracking difference",
  time_on_target_percent: "Time tracking was clear",
  total_catch_up_saccades: "Catch-up eye movements",
};

function labelFor(key: string): string {
  return LABELS[key] ?? key.replace(/_/g, " ");
}

function valueFor(key: string, value: number | string | null): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string") return value;
  if (key.endsWith("_percent")) return `${value}%`;
  if (key.endsWith("_ms")) return `${value} ms`;
  if (key.endsWith("_px")) return `${value} px`;
  if (key.includes("gain")) return value.toFixed(2);
  return `${value}`;
}

// A short, research-only explanation shown under certain activities.
function explanation(task: string): string | null {
  switch (task) {
    case "gap_overlap":
      return (
        "In the gap condition the center dot disappears just before the new dot " +
        "appears; in the overlap condition it stays on screen. Comparing the two " +
        "shows how the timing of the center dot affects reaction speed. This is a " +
        "research measure only."
      );
    case "smooth_pursuit":
      return (
        "“Gain” compares how fast your eyes moved to how fast the dot moved. A value " +
        "near 1.0 means your eyes closely followed the dot. This is a research " +
        "measure only."
      );
    case "antisaccade":
      return (
        "This activity asks you to look away from a sudden dot. Looking toward it " +
        "first is common and is simply recorded as part of the data. This is a " +
        "research measure only."
      );
    default:
      return null;
  }
}

function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function ResultsSummary({ s }: { s: SessionSummary }) {
  const isPursuit = s.technical_task_name === "smooth_pursuit";
  const metricEntries = Object.entries(s.task_metrics || {});
  const note = explanation(String(s.technical_task_name));

  return (
    <div className="grid" style={{ gap: 22 }}>
      {/* Header */}
      <div className="results-head">
        <div>
          <span className="eyebrow">Session summary</span>
          <h2 style={{ marginBottom: 4 }}>{s.activity_name}</h2>
          <p className="muted" style={{ marginBottom: 0 }}>
            {fmtDate(s.date_time)} · Session {s.session_id}
          </p>
        </div>
        <QualityBadge label={s.tracking_quality_label} />
      </div>

      {/* Stat tiles */}
      <div className="stats">
        <div className="stat">
          <div className="k">Rounds completed</div>
          <div className="v">{s.rounds_completed ?? "—"}</div>
        </div>
        <div className="stat">
          <div className="k">Usable eye-tracking data</div>
          <div className="v">
            {s.usable_data_percent ?? "—"}
            <span className="u">%</span>
          </div>
        </div>
        <div className="stat">
          <div className="k">Blinks</div>
          <div className="v">{s.blink_count ?? "—"}</div>
        </div>
        <div className="stat">
          <div className="k">
            {isPursuit ? "Tracking closeness" : "Average response"}
          </div>
          <div className="v">
            {isPursuit
              ? (s.task_metrics?.mean_pursuit_gain as number | undefined)?.toFixed?.(
                  2,
                ) ?? "—"
              : s.average_response_time_ms ?? "—"}
            {!isPursuit && s.average_response_time_ms != null && (
              <span className="u"> ms</span>
            )}
          </div>
        </div>
      </div>

      {/* Activity details */}
      <div className="card">
        <h3 className="mb-2">Activity details</h3>
        {metricEntries.length ? (
          metricEntries.map(([k, v]) => (
            <div className="metric-row" key={k}>
              <span className="k">{labelFor(k)}</span>
              <span className="v">{valueFor(k, v)}</span>
            </div>
          ))
        ) : (
          <p className="muted mb-0">No per-round metrics available.</p>
        )}
        {note && <div className="note mt-3">{note}</div>}
      </div>

      {/* Recommendations */}
      {s.recommendations?.length > 0 && (
        <div className="card">
          <h3 className="mb-2">Suggestions for next time</h3>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {s.recommendations.map((r, i) => (
              <li key={i} className="muted" style={{ marginBottom: 6 }}>
                {r}
              </li>
            ))}
          </ul>
        </div>
      )}

      <DisclaimerBox text={s.disclaimer} />
    </div>
  );
}
