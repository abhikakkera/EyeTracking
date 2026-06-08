// PDEYE API client. All requests go to /api/* which Next.js rewrites to the
// local FastAPI backend (see next.config.js). Override with NEXT_PUBLIC_API_BASE.

import type {
  ExportsResponse,
  FrameResult,
  SessionRow,
  SessionSummary,
  StartTestRequest,
  StartTestResponse,
  TaskFrameContext,
  TestStatusResponse,
  WebConfig,
  WebEvent,
  WebSessionStatusResp,
  WebStartResponse,
} from "@/lib/types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    ...init,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

export const api = {
  health: () => req<{ status: string; version: string }>("/api/health"),

  // Tests
  startTest: (body: StartTestRequest) =>
    req<StartTestResponse>("/api/tests/start", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getStatus: (sessionId: string) =>
    req<TestStatusResponse>(`/api/tests/status/${sessionId}`),
  stopTest: (sessionId: string) =>
    req<TestStatusResponse>(`/api/tests/stop/${sessionId}`, { method: "POST" }),

  // Results
  latestResult: () => req<SessionSummary>("/api/results/latest"),
  getResult: (sessionId: string) =>
    req<SessionSummary>(`/api/results/${sessionId}`),
  openFolder: () =>
    req<{ opened: boolean; path: string }>("/api/results/open-folder", {
      method: "POST",
    }),
  makeReport: (sessionId: string) =>
    req<{ html_report_path: string }>(`/api/results/${sessionId}/report`, {
      method: "POST",
    }),

  // Sessions / history
  listSessions: (limit = 100) =>
    req<SessionRow[]>(`/api/sessions?limit=${limit}`),
  getSession: (sessionId: string) =>
    req<SessionSummary>(`/api/sessions/${sessionId}`),
  getExports: (sessionId: string) =>
    req<ExportsResponse>(`/api/sessions/${sessionId}/exports`),

  // Download URL for a given export kind (open directly in the browser)
  downloadUrl: (sessionId: string, kind: string) =>
    `${BASE}/api/results/${sessionId}/download/${kind}`,

  // ---- Web task mode (in-browser) ----
  webConfig: () => req<WebConfig>("/api/web-config"),

  startWebSession: (body: {
    task_type: string;
    participant_id?: string;
    screen_width: number;
    screen_height: number;
    task_config?: Record<string, unknown>;
  }) =>
    req<WebStartResponse>("/api/web-sessions/start", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  sendEvent: (sessionId: string, event: WebEvent) =>
    req<{ ok: boolean }>(`/api/web-sessions/${sessionId}/event`, {
      method: "POST",
      body: JSON.stringify(event),
    }),

  completeWebSession: (sessionId: string) =>
    req<SessionSummary>(`/api/web-sessions/${sessionId}/complete`, {
      method: "POST",
    }),

  cancelWebSession: (sessionId: string) =>
    req<WebSessionStatusResp>(`/api/web-sessions/${sessionId}/cancel`, {
      method: "POST",
    }),

  webStatus: (sessionId: string) =>
    req<WebSessionStatusResp>(`/api/web-sessions/${sessionId}/status`),

  /**
   * Upload one webcam frame (JPEG blob) + task context as multipart/form-data.
   * Note: do NOT set Content-Type — the browser adds the multipart boundary.
   */
  sendFrame: async (
    sessionId: string,
    blob: Blob,
    meta: TaskFrameContext & {
      browser_timestamp_ms: number;
      task_start_timestamp_ms: number;
    },
    timeoutMs = 4000,
  ): Promise<FrameResult> => {
    const fd = new FormData();
    fd.append("file", blob, "frame.jpg");
    fd.append("meta", JSON.stringify(meta));

    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const res = await fetch(`${BASE}/api/web-sessions/${sessionId}/frame`, {
        method: "POST",
        body: fd,
        signal: ctrl.signal,
      });
      if (!res.ok) throw new ApiError(`frame ${res.status}`, res.status);
      return (await res.json()) as FrameResult;
    } finally {
      clearTimeout(timer);
    }
  },
};
