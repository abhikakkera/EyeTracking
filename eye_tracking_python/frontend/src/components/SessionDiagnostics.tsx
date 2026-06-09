import type { SessionDiagnostics as Diag } from "@/lib/types";
import { formatCount, formatConfidence, formatNumber, formatPercent } from "@/lib/format";

// Collapsed-by-default developer panel. Not shown to participants unless they
// expand it. Useful for debugging why a session was unclear.
export default function SessionDiagnostics({ d }: { d?: Diag | null }) {
  if (!d) return null;

  const rows: [string, string][] = [
    ["Frames received", formatCount(d.total_frames_received)],
    ["Frames processed", formatCount(d.total_frames_processed)],
    ["Frames with face", formatCount(d.frames_with_face_detected)],
    ["Frames with eye", formatCount(d.frames_with_eye_detected)],
    ["Frames with pupil / gaze", formatCount(d.frames_with_pupil_or_gaze_detected)],
    [
      "Usable eye-tracking frames",
      `${formatCount(d.usable_eye_tracking_frames)} (${formatPercent(d.usable_eye_tracking_percent)})`,
    ],
    ["Frames per round", formatNumber(d.frames_per_trial, 1)],
    ["Gaze samples available", formatCount(d.gaze_samples_available)],
    ["Average confidence", formatConfidence(d.average_confidence)],
    ["Task events received", formatCount(d.task_events_received)],
    ["Target events received", formatCount(d.target_onset_events_received)],
    ["Total trials", formatCount(d.total_trials)],
    ["Valid trials", formatCount(d.valid_trials)],
    ["Unclear trials", formatCount(d.unclear_trials)],
    ["Bad trials", formatCount(d.bad_trials)],
    ["Main unclear reason", d.main_unclear_reason ?? "—"],
  ];

  const reasons = d.missing_gaze_reason_counts || {};
  const reasonEntries = Object.entries(reasons).sort((a, b) => b[1] - a[1]);

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

      {reasonEntries.length > 0 && (
        <div className="mt-2">
          <div className="k small mb-1">Why frames were not usable</div>
          {reasonEntries.map(([reason, count]) => (
            <div className="diag-row" key={reason}>
              <span className="k mono">{reason}</span>
              <span className="v mono">{count}</span>
            </div>
          ))}
        </div>
      )}

      <p className="muted small mt-2 mb-0">
        These numbers describe camera/tracking quality only. They are not a medical
        measurement.
      </p>
    </details>
  );
}
