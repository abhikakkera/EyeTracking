import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { api } from "@/lib/api";

function jsonResponse(body: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    statusText: ok ? "OK" : "Error",
    json: async () => body,
  } as unknown as Response;
}

describe("api client (web task functions)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("startWebSession POSTs JSON to the right route", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ session_id: "abc12345", status: "ready" }));

    const res = await api.startWebSession({
      task_type: "prosaccade",
      screen_width: 1280,
      screen_height: 720,
    });

    expect(res.session_id).toBe("abc12345");
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/web-sessions/start");
    expect((init as RequestInit).method).toBe("POST");
    expect(String((init as RequestInit).body)).toContain("prosaccade");
  });

  it("sendEvent posts an event payload", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ ok: true }));

    await api.sendEvent("sid123", { type: "trial_started", timestamp_ms: 100 });
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/web-sessions/sid123/event");
    expect(String((init as RequestInit).body)).toContain("trial_started");
  });

  it("sendFrame uploads multipart form data", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        jsonResponse({
          frame_number: 0,
          tracking_status: "good",
          distance_status: "good",
          guidance_message: "ok",
        }),
      );

    const blob = new Blob([new Uint8Array([1, 2, 3])], { type: "image/jpeg" });
    const res = await api.sendFrame(
      "sid123",
      blob,
      {
        trial_id: "t1",
        trial_number: 1,
        task_phase: "target",
        target_visible: true,
        target_x: 0.85,
        target_y: 0.5,
        target_direction: "right",
        condition: "none",
        fixation_visible: false,
        browser_timestamp_ms: 123,
        task_start_timestamp_ms: 0,
      },
      2000,
    );

    expect(res.tracking_status).toBe("good");
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/web-sessions/sid123/frame");
    expect((init as RequestInit).method).toBe("POST");
    expect((init as RequestInit).body).toBeInstanceOf(FormData);
  });

  it("login posts credentials to the auth route", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        jsonResponse({ token: "t", user: { id: 1, email: "a@b.com", name: "A" } }),
      );

    const res = await api.login({ email: "a@b.com", password: "password123" });
    expect(res.token).toBe("t");
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/auth/login");
    expect((init as RequestInit).method).toBe("POST");
    expect(String((init as RequestInit).body)).toContain("a@b.com");
  });
});
