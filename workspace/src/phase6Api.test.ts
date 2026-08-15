import { afterEach, describe, expect, it, vi } from "vitest";
import { Phase6Api } from "./phase6Api";

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "content-type": "application/json" },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Phase6Api read-only authority", () => {
  it("keeps sanitized health unauthenticated", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ ok: true }));
    const api = new Phase6Api({ baseUrl: "/origins-phase6", token: "secret" });
    await api.health();
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/origins-phase6/v1/health");
    expect((init as RequestInit).method).toBe("GET");
    expect(new Headers((init as RequestInit).headers).has("authorization")).toBe(false);
  });

  it("loads the consolidated device projection with GET only", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ mode: "device_read_only" }));
    const api = new Phase6Api({ baseUrl: "/origins-phase6", token: "secret" });
    await api.device();
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/origins-phase6/v1/device");
    expect((init as RequestInit).method).toBe("GET");
    expect(new Headers((init as RequestInit).headers).get("authorization")).toBe("Bearer secret");
    expect((init as RequestInit).body).toBeUndefined();
  });

  it("exposes only read projection methods", () => {
    const methods = Object.getOwnPropertyNames(Phase6Api.prototype).filter((name) => name !== "constructor" && name !== "request");
    expect(methods.sort()).toEqual(["device", "gateway", "health", "xray"]);
  });
});
