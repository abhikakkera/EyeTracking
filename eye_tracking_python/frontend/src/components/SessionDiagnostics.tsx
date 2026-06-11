import type { SessionDiagnostics as Diag } from "@/lib/types";
import { formatCount, formatConfidence, formatNumber, formatPercent } from "@/lib/format";

// Collapsed-by-default developer panel. Not shown to participants unless they
// expand it. Useful for debugging why a session was unclear — now distinguishes
// "could we track this round" from "did they respond", and shows WHEN no-face
// frames happened (by phase + by trial).
export default function SessionDiagnostics({ d }: { d?: Diag | null }) {
  if (!d) return null;

  const rows: [string, string][] = [
    ["Frames received", formatCount(d.total_frames_received)],
    ["Frames with face", formatCount(d.frames_with_face_detected)],
    ["Frames with eye", formatCount(d.frames_with_eye_detected)],
    ["Frames with pupil / gaze", formatCount(d.frames_with_pupil_or_gaze_detected)],
    [
      "Usable eye-tracking frames (task only)",
      `${formatCount(d.usable_eye_tracking_frames)} (${formatPercent(d.usable_eye_tracking_percent)})`,
    ],
    ["Frames per round", formatNumber(d.frames_per_trial, 1)],
    ["Average confidence", formatConfidence(d.average_confidence)],
    ["Total rounds", formatCount(d.total_trials)],
    ["Well-tracked rounds", formatCount(d.well_tracked_trials ?? d.valid_trials)],
    ["Rounds with a detected response", formatCount(d.rounds_with_response ?? d.valid_trials)],
    ["Rounds we couldn't track", formatCount(d.untrackable_trials ?? d.unclear_trials)],
    ["Main reason a round was unclear", d.main_unclear_reason ?? "— (all rounds tracked)"],
  ];

  const nf = d.no_face;
  const phaseEntries = Object.entries(nf?.by_phase || {}).sort((a, b) => b[1] - a[1]);
  const trials = d.trials_quality || [];

  return (
    <details className="card diag mt-3">
      <summary>Developer diagnostics</summary>

      <div className="diag-grid mt-2">
        {rows.map(([k, v]) => (
          <div className="diag-row" key={k}>
            <span className="k">{k}</span>
            <span className="v mono">{v}</span>
          </div>
        ))}
      </div>

      {/* No-face timing — WHERE the missing-face frames actually happened */}
      {nf && (
        <div className="mt-3">
          <div className="k small mb-1">
            No-face frames during the task: {formatCount(nf.total_frames)} ({formatPercent(nf.percent)})
            {typeof nf.longest_streak_ms === "number" && nf.longest_streak_ms > 0
              ? ` · longest gap ${formatNumber(nf.longest_streak_ms, 0)} ms`
              : ""}
          </div>
          {phaseEntries.length > 0 && (
            <div className="diag-grid">
              {phaseEntries.map(([phase, count]) => (
                <div className="diag-row" key={phase}>
                  <span className="k mono">no_face · {phase}</span>
                  <span className="v mono">{count}</span>
                </div>
              ))}
            </div>
          )}
          <p className="muted small mt-1 mb-0">
            Frames outside the <span className="mono">task</span> phase (setup, countdown,
            between rounds) are recorded but never counted against tracking quality.
          </p>
        </div>
      )}

      {/* Per-trial debug table — makes it obvious why a round was marked unclear */}
      {trials.length > 0 && (
        <div className="mt-3" style={{ overflowX: "auto" }}>
          <div className="k small mb-1">Per-round detail</div>
          <table className="diag-table">
            <thead>
              <tr>
                <th>#</th>
                <th>dir</th>
                <th>frames</th>
                <th>usable%</th>
                <th>resp.win%</th>
                <th>no-face</th>
                <th>blinks</th>
                <th>response</th>
                <th>RT (ms)</th>
                <th>quality</th>
                <th>reason / flags</th>
              </tr>
            </thead>
            <tbody>
              {trials.map((t, i) => (
                <tr key={t.trial_id || i} className={`tq-${t.trial_quality}`}>
                  <td>{t.trial_number ?? i + 1}</td>
                  <td className="mono">{t.target_direction ?? "—"}</td>
                  <td className="mono">{formatCount(t.total_trial_frames)}</td>
                  <td className="mono">{formatPercent(t.usable_trial_frame_percent)}</td>
                  <td className="mono">{formatPercent(t.usable_response_window_percent)}</td>
                  <td className="mono">
                    {formatCount(t.no_face_frame_count)}
                    {t.no_face_near_target_onset ? " ⚑" : ""}
                  </td>
                  <td className="mono">{formatCount(t.blink_frame_count)}</td>
                  <td className="mono">{t.response_detected ? "yes" : "no"}</td>
                  <td className="mono">{formatNumber(t.reaction_time_ms, 0)}</td>
                  <td className="mono">{t.trial_quality}</td>
                  <td className="mono small">
                    {t.unclear_reason || (t.quality_flags?.length ? t.quality_flags.join(", ") : "—")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted small mt-1 mb-0">⚑ = face left the view near the moment the dot appeared.</p>
        </div>
      )}

      {d.stabilization_overridden ? (
        <p className="muted small mt-2 mb-0">
          Note: this session was started before tracking was fully steady (“Start anyway”),
          so some rounds may be lower-confidence.
        </p>
      ) : null}

      <p className="muted small mt-2 mb-0">
        These numbers describe camera/tracking quality only. They are not a medical
        measurement.
      </p>
    </details>
  );
}
