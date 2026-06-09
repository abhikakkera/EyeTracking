import type { SessionSummary, TaskMetrics } from "@/lib/types";
import QualityBadge from "@/components/QualityBadge";
import DisclaimerBox from "@/components/DisclaimerBox";
import {
  formatCount,
  formatGain,
  formatMilliseconds,
  formatMsDelta,
  formatPercent,
  formatPx,
  formatSpeed,
} from "@/lib/format";

type Row = { label: string; value: string };

// Build ONLY the rows that are meaningful for each task type.
function rowsForTask(task: string, m: TaskMetrics): Row[] {
  switch (task) {
    case "prosaccade":
      return [
        { label: "Average response time", value: formatMilliseconds(m.average_response_time_ms) },
        { label: "Fastest response", value: formatMilliseconds(m.fastest_response_ms) },
        { label: "Successful clear rounds", value: formatCount(m.successful_clear_rounds) },
        { label: "Rounds with unclear tracking", value: formatCount(m.unclear_rounds) },
        { label: "Rounds with a response", value: formatPercent(m.rounds_with_response_percent) },
        { label: "Average eye-movement speed", value: formatSpeed(m.average_eye_movement_speed_px_per_sec) },
      ];
    case "antisaccade":
      return [
        { label: "Correct-direction rounds", value: formatCount(m.correct_direction_rounds) },
        { label: "Average response time", value: formatMilliseconds(m.average_response_time_ms) },
        { label: "Self-corrections", value: formatCount(m.self_corrections) },
        { label: "Looked toward the dot first", value: formatPercent(m.looked_toward_first_percent) },
        { label: "Rounds with unclear tracking", value: formatCount(m.unclear_rounds) },
      ];
    case "gap_overlap":
      return [
        { label: "Average response — gap", value: formatMilliseconds(m.average_response_time_gap_ms) },
        { label: "Average response — overlap", value: formatMilliseconds(m.average_response_time_overlap_ms) },
        { label: "Gap effect", value: formatMsDelta(m.gap_effect_ms) },
        { label: "Valid gap rounds", value: formatCount(m.valid_gap_rounds) },
        { label: "Valid overlap rounds", value: formatCount(m.valid_overlap_rounds) },
      ];
    case "smooth_pursuit":
      return [
        { label: "Tracking closeness (gain)", value: formatGain(m.tracking_gain) },
        { label: "Average tracking difference", value: formatPx(m.average_tracking_difference_px) },
        { label: "Time tracking was clear", value: formatPercent(m.time_tracking_clear_percent) },
        { label: "Catch-up eye movements", value: formatCount(m.catch_up_eye_movements) },
      ];
    default:
      return [];
  }
}

function explanation(task: string): string | null {
  switch (task) {
    case "gap_overlap":
      return (
        "In the gap condition the center dot disappears just before the new dot " +
        "appears; in the overlap condition it stays on screen. Comparing the two " +
        "shows how the timing of the center dot affects reaction speed. Research measure only."
      );
    case "smooth_pursuit":
      return (
        "“Gain” compares how fast your eyes moved to how fast the dot moved. A value " +
        "near 1.0 means your eyes closely followed the dot. Research measure only."
      );
    case "antisaccade":
      return (
        "This activity asks you to look away from a sudden dot. Looking toward it " +
        "first is common and is simply recorded as part of the data. Research measure only."
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
  const rows = rowsForTask(String(s.technical_task_name), s.task_metrics || {});
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

      {/* Honest banner when the camera couldn't capture clear eye movements */}
      {s.notes && (
        <div className="note-warn">
          <strong>{s.notes}</strong>
          <div className="muted small mt-1">
            This usually means the camera couldn’t see your eyes clearly enough. Try the
            suggestions below and run the activity again.
          </div>
        </div>
      )}

      {/* Stat tiles */}
      <div className="stats">
        <div className="stat">
          <div className="k">Rounds completed</div>
          <div className="v">{formatCount(s.rounds_completed)}</div>
        </div>
        <div className="stat">
          <div className="k">Usable eye-tracking data</div>
          <div className="v">{formatPercent(s.usable_data_percent)}</div>
        </div>
        <div className="stat">
          <div className="k">Blinks</div>
          <div className="v">{formatCount(s.blink_count)}</div>
        </div>
        <div className="stat">
          <div className="k">{isPursuit ? "Tracking closeness" : "Average response"}</div>
          <div className="v">
            {isPursuit
              ? formatGain(s.task_metrics?.tracking_gain)
              : formatMilliseconds(s.average_response_time_ms)}
          </div>
        </div>
      </div>

      {/* Activity details — task-appropriate rows only */}
      <div className="card">
        <h3 className="mb-2">Activity details</h3>
        {rows.length ? (
          rows.map((r) => (
            <div className="metric-row" key={r.label}>
              <span className="k">{r.label}</span>
              <span className="v">{r.value}</span>
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
