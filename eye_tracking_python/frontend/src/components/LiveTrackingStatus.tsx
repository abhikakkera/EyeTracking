"use client";

import type { FrameResult } from "@/lib/types";

function dotColor(status?: string): string {
  switch (status) {
    case "good":
      return "var(--green)";
    case "questionable":
      return "var(--amber)";
    default:
      return "var(--danger)";
  }
}

export default function LiveTrackingStatus({
  result,
  debug = false,
  uploadFps,
  subtle = false,
}: {
  result: FrameResult | null;
  debug?: boolean;
  uploadFps?: number;
  subtle?: boolean;
}) {
  const message = result?.guidance_message ?? "Connecting to the camera…";
  const color = dotColor(result?.tracking_status);

  return (
    <div className={`live-status${subtle ? " subtle" : ""}`}>
      <span
        className="live-dot"
        style={{ background: color }}
        aria-hidden
      />
      <span className="live-msg">{message}</span>

      {debug && result && (
        <span className="live-debug">
          conf {result.confidence?.toFixed?.(2) ?? "—"} · gaze{" "}
          {result.gaze_x?.toFixed?.(2) ?? "—"},{result.gaze_y?.toFixed?.(2) ?? "—"} ·{" "}
          {uploadFps ?? 0} fps · {result.tracking_status}
        </span>
      )}
    </div>
  );
}
