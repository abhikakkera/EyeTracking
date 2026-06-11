// Ocula frontend types — mirror of backend/db/models.py

export interface User {
  id: number;
  email: string;
  name: string;
  created_at?: number | null;
}

export interface AuthResponse {
  token: string;
  user: User;
}

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

export interface TrialQuality {
  trial_id?: string;
  trial_number?: number | null;
  target_direction?: string | null;
  trial_quality?: "clear" | "unclear" | "bad" | string;
  unclear_reason?: string | null;
  total_trial_frames?: number | null;
  usable_trial_frames?: number | null;
  usable_trial_frame_percent?: number | null;
  no_face_frame_count?: number | null;
  blink_frame_count?: number | null;
  response_window_frames?: number | null;
  usable_response_window_frames?: number | null;
  usable_response_window_percent?: number | null;
  no_face_near_target_onset?: boolean | null;
  no_face_in_response_window?: boolean | null;
  longest_no_face_streak_ms?: number | null;
  short_dropout?: boolean | null;
  response_detected?: boolean | null;
  reaction_time_ms?: number | null;
  quality_flags?: string[];
}

export interface NoFaceDiagnostics {
  total_frames?: number | null;
  percent?: number | null;
  by_phase?: Record<string, number>;
  by_trial?: {
    trial_id?: string;
    trial_number?: number | null;
    no_face_frames?: number | null;
    no_face_near_target_onset?: boolean | null;
    no_face_in_response_window?: boolean | null;
    longest_streak_ms?: number | null;
  }[];
  longest_streak_frames?: number | null;
  longest_streak_ms?: number | null;
}

export interface SessionDiagnostics {
  total_frames_received?: number | null;
  total_frames_processed?: number | null;
  frames_with_face_detected?: number | null;
  frames_with_eye_detected?: number | null;
  frames_with_pupil_or_gaze_detected?: number | null;
  usable_eye_tracking_frames?: number | null;
  usable_eye_tracking_percent?: number | null;
  frames_per_trial?: number | null;
  gaze_samples_available?: number | null;
  average_confidence?: number | null;
  total_trials?: number | null;
  valid_trials?: number | null;
  well_tracked_trials?: number | null;
  rounds_with_response?: number | null;
  untrackable_trials?: number | null;
  unclear_trials?: number | null;
  bad_trials?: number | null;
  task_events_received?: number | null;
  target_onset_events_received?: number | null;
  missing_gaze_reason_counts?: Record<string, number>;
  main_unclear_reason?: string | null;
  trials_quality?: TrialQuality[];
  no_face?: NoFaceDiagnostics | null;
  frames_by_recording_phase?: Record<string, number>;
  stabilization_overridden?: boolean | null;
}

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
  diagnostics?: SessionDiagnostics | null;
  notes?: string | null;
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
  stabilization_window_ms?: number;
  stabilization_min_usable_ratio?: number;
  stabilization_min_samples?: number;
  task_face_loss_warn_ms?: number;
}

// Coarse recording phase tagged on every uploaded frame. Only "task" frames
// count toward usable% / trial quality on the backend.
export type RecordingPhase =
  | "setup"
  | "stabilization"
  | "countdown"
  | "task"
  | "between_trials"
  | "complete";

// Per-frame task context the browser tags each uploaded frame with.
export interface TaskFrameContext {
  trial_id: string;
  trial_number: number;
  task_phase: string;
  recording_phase?: RecordingPhase;
  target_visible: boolean;
  target_x: number;
  target_y: number;
  target_direction: string;
  condition: string;
  fixation_visible: boolean;
}
