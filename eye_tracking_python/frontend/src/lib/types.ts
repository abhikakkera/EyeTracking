// PDEYE frontend types — mirror of backend/db/models.py

export type TaskType =
  | "prosaccade"
  | "antisaccade"
  | "gap_overlap"
  | "smooth_pursuit";

export type TestStatus =
  | "preparing"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "not_found";

export interface StartTestRequest {
  task_type: TaskType;
  participant_id?: string;
  mode?: string;
  trials?: number;
  pattern?: string;
  cycles?: number;
}

export interface StartTestResponse {
  session_id: string;
  status: TestStatus;
  task_type: TaskType;
  error?: string | null;
}

export interface TestStatusResponse {
  session_id: string;
  status: TestStatus;
  task_type?: TaskType | null;
  error?: string | null;
}

// A flexible bag of per-task metrics (shape varies by task type).
export type TaskMetrics = Record<string, number | string | null>;

export interface SessionSummary {
  session_id: string;
  technical_task_name: TaskType | string;
  activity_name: string;
  date_time?: string | null;
  status: string;
  subject_id: string;
  duration_sec?: number | null;
  fps?: number | null;
  tracking_quality_label?: string | null;
  usable_data_percent?: number | null;
  average_confidence?: number | null;
  blink_count?: number | null;
  rounds_completed?: number | null;
  average_response_time_ms?: number | null;
  task_metrics: TaskMetrics;
  recommendations: string[];
  exports: Record<string, string>;
  disclaimer: string;
}

export interface SessionRow {
  session_id: string;
  date_time?: string | null;
  task_type?: string | null;
  activity_name?: string | null;
  status?: string | null;
  tracking_quality_label?: string | null;
  usable_data_percent?: number | null;
  rounds_completed?: number | null;
  average_response_time_ms?: number | null;
}

export interface ExportsResponse {
  session_id: string;
  exports: Record<string, string>;
}

// ---------------------------------------------------------------------------
// Web task mode (in-browser stimulus + streamed frames)
// ---------------------------------------------------------------------------

export interface WebStartResponse {
  session_id: string;
  status: string;
}

export type TrackingStatus = "good" | "questionable" | "bad";
export type DistanceStatus = "good" | "too_close" | "too_far" | "unknown";

export interface FrameResult {
  frame_number: number;
  tracking_status: TrackingStatus;
  distance_status: DistanceStatus;
  guidance_message: string;
  gaze_x?: number | null;
  gaze_y?: number | null;
  confidence?: number | null;
  blink_detected?: boolean | null;
  face_detected?: boolean | null;
}

export interface WebEvent {
  type: string;
  timestamp_ms: number;
  trial_id?: string;
  trial_number?: number;
  direction?: string;
  condition?: string;
  cycle_number?: number;
  target_x?: number;
  target_y?: number;
  task_start_timestamp_ms?: number;
}

export interface WebSessionStatusResp {
  session_id: string;
  status: string;
  frames_received: number;
  events_received: number;
}

export interface WebConfig {
  upload_fps: number;
  jpeg_quality: number;
  max_width: number;
  max_height: number;
  backend_timeout_ms: number;
}

// Per-frame task context the browser tags each uploaded frame with.
export interface TaskFrameContext {
  trial_id: string;
  trial_number: number;
  task_phase: string;
  target_visible: boolean;
  target_x: number;
  target_y: number;
  target_direction: string;
  condition: string;
  fixation_visible: boolean;
}
