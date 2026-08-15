import { afterEach, describe, expect, it, vi } from "vitest";
import { Phase7Api, Phase7ApiError } from "./phase7Api";

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; vi.restoreAllMocks(); });

function response(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

describe("Phase7Api", () => {
  it("keeps public health unauthenticated", async () => {
    const spy = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(new Headers(init?.headers).has("authorization")).toBe(false);
      return response(200, { ok: true, runtime_authority_expansion: false, model_self_approval: false });
    });
    globalThis.fetch = spy as typeof fetch;
    const health = await new Phase7Api({ baseUrl: "/origins-phase7/", token: "" }).health();
    expect(health.runtime_authority_expansion).toBe(false);
    expect(health.model_self_approval).toBe(false);
  });

  it("requires bearer for protected evolution state", async () => {
    const api = new Phase7Api({ baseUrl: "/origins-phase7", token: "" });
    await expect(api.evolutions()).rejects.toMatchObject({ status: 401 });
  });

  it("never injects owner approval or runtime authority fields", async () => {
    const spy = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const decoded = JSON.parse(String(init?.body ?? "{}"));
      expect(decoded.owner_approved).toBeUndefined();
      expect(decoded.approval_state).toBeUndefined();
      expect(decoded.runtime_authority_activated).toBeUndefined();
      expect(new Headers(init?.headers).get("authorization")).toBe("Bearer proof-token");
      return response(201, { evolution_id: "e1", state: "proposal_ready" });
    });
    globalThis.fetch = spy as typeof fetch;
    const api = new Phase7Api({ baseUrl: "/origins-phase7", token: "proof-token" });
    await api.confirmGap({ mission_id: "m1", capability_id: "cap" });
  });

  it("uses explicit owner decision endpoints", async () => {
    const calls: Array<{ url: string; body: unknown }> = [];
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(input), body: init?.body ? JSON.parse(String(init.body)) : null });
      return response(200, { state: "promoted" });
    }) as typeof fetch;
    const api = new Phase7Api({ baseUrl: "/origins-phase7", token: "proof-token" });
    await api.decide("evo 7", "promote", "owner");
    expect(calls[0]).toEqual({
      url: "/origins-phase7/v1/evolutions/evo%207/decision",
      body: { decision: "promote", decided_by: "owner" },
    });
  });

  it("surfaces server conflict details", async () => {
    globalThis.fetch = vi.fn(async () => response(409, { error: "CapabilityEvolutionError", detail: "canary has not passed" })) as typeof fetch;
    const api = new Phase7Api({ baseUrl: "/origins-phase7", token: "proof-token" });
    await expect(api.resume("e1")).rejects.toEqual(new Phase7ApiError(409, "canary has not passed", expect.anything()));
  });
});
