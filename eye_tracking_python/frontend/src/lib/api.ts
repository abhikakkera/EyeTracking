// Ocula API client. Requests go to /api/* which Next.js rewrites to the local
// FastAPI backend (see next.config.js). Override with NEXT_PUBLIC_API_BASE.
//
// AUTH NOTE (local prototype): the bearer token is kept in localStorage and sent
// as `Authorization: Bearer`. This is simple and reliable for a local single-
// machine prototype, but localStorage is readable by any script on the page, so
// it is vulnerable to XSS. A production build should use httpOnly cookies.

import type {
  AuthResponse,
  ExportsResponse,
  FrameResult,
  SessionRow,
  SessionSummary,
  StartTestRequest,
  StartTestResponse,
  TaskFrameContext,
  TestStatusResponse,
  User,
  WebConfig,
  WebEvent,
  WebSessionStatusResp,
  WebStartResponse,
} from "@/lib/types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";
const TOKEN_KEY = "ocula_token";

// ---- token store ----
export const tokenStore = {
  get(): string | null {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(TOKEN_KEY);
  },
  set(token: string) {
    if (typeof window !== "undefined") window.localStorage.setItem(TOKEN_KEY, token);
  },
  clear() {
    if (typeof window !== "undefined") window.localStorage.removeItem(TOKEN_KEY);
  },
};

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const h: Record<string, string> = { ...extra };
  const t = tokenStore.get();
  if (t) h["Authorization"] = `Bearer ${t}`;
  return h;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    cache: "no-store",
    ...init,
    headers: authHeaders({ "Content-Type": "application/json", ...(init?.headers as object) }),
  });
  if (!res.ok) {
    if (res.status === 401 && typeof window !== "undefined") tokenStore.clear();
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

export const api = {
  health: () => req<{ status: string; version: string }>("/api/health"),

  // ---- Auth ----
  signup: (body: { name: string; email: string; password: string }) =>
    req<AuthResponse>("/api/auth/signup", { method: "POST", body: JSON.stringify(body) }),
  login: (body: { email: string; password: string }) =>
    req<AuthResponse>("/api/auth/login", { method: "POST", body: JSON.stringify(body) }),
  logout: () => req<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  me: () => req<User>("/api/auth/me"),
  updateName: (name: string) =>
    req<User>("/api/auth/me", { method: "PATCH", body: JSON.stringify({ name }) }),

  // Tests (legacy CLI/desktop)
  startTest: (body: StartTestRequest) =>
    req<StartTestResponse>("/api/tests/start", { method: "POST", body: JSON.stringify(body) }),
  getStatus: (sessionId: string) => req<TestStatusResponse>(`/api/tests/status/${sessionId}`),
  stopTest: (sessionId: string) =>
    req<TestStatusResponse>(`/api/tests/stop/${sessionId}`, { method: "POST" }),

  // Results
  latestResult: () => req<SessionSummary>("/api/results/latest"),
  getResult: (sessionId: string) => req<SessionSummary>(`/api/results/${sessionId}`),
  openFolder: () =>
    req<{ opened: boolean; path: string }>("/api/results/open-folder", { method: "POST" }),
  makeReport: (sessionId: string) =>
    req<{ html_report_path: string }>(`/api/results/${sessionId}/report`, { method: "POST" }),

  // Sessions / history
  listSessions: (limit = 100) => req<SessionRow[]>(`/api/sessions?limit=${limit}`),
  getSession: (sessionId: string) => req<SessionSummary>(`/api/sessions/${sessionId}`),
  getExports: (sessionId: string) => req<ExportsResponse>(`/api/sessions/${sessionId}/exports`),

  /** Download an export with auth, via blob (direct <a> links can't carry the token). */
  downloadExport: async (sessionId: string, kind: string, filename?: string) => {
    const res = await fetch(`${BASE}/api/results/${sessionId}/download/${kind}`, {
      headers: authHeaders(),
    });
    if (!res.ok) throw new ApiError(`download ${res.status}`, res.status);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename || `${sessionId}_${kind}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  // ---- Web task mode (in-browser) ----
  webConfig: () => req<WebConfig>("/api/web-config"),
  startWebSession: (body: {
    task_type: string;
    participant_id?: string;
    screen_width: number;
    screen_height: number;
    task_config?: Record<string, unknown>;
  }) => req<WebStartResponse>("/api/web-sessions/start", { method: "POST", body: JSON.stringify(body) }),
  sendEvent: (sessionId: string, event: WebEvent) =>
    req<{ ok: boolean }>(`/api/web-sessions/${sessionId}/event`, {
      method: "POST",
      body: JSON.stringify(event),
    }),
  completeWebSession: (sessionId: string) =>
    req<SessionSummary>(`/api/web-sessions/${sessionId}/complete`, { method: "POST" }),
  cancelWebSession: (sessionId: string) =>
    req<WebSessionStatusResp>(`/api/web-sessions/${sessionId}/cancel`, { method: "POST" }),
  webStatus: (sessionId: string) =>
    req<WebSessionStatusResp>(`/api/web-sessions/${sessionId}/status`),

  /** Upload one webcam frame (JPEG) + task context as multipart/form-data. */
  sendFrame: async (
    sessionId: string,
    blob: Blob,
    meta: TaskFrameContext & { browser_timestamp_ms: number; task_start_timestamp_ms: number },
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
        headers: authHeaders(),
      });
      if (!res.ok) throw new ApiError(`frame ${res.status}`, res.status);
      return (await res.json()) as FrameResult;
    } finally {
      clearTimeout(timer);
    }
  },
};
