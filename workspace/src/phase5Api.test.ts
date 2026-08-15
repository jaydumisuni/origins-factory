import { afterEach, describe, expect, it, vi } from "vitest";
import { Phase5Api } from "./phase5Api";

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "content-type": "application/json" },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Phase5Api authority boundaries", () => {
  it("keeps public health unauthenticated", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ ok: true }));
    const api = new Phase5Api({ originsBaseUrl: "/origins-api", phase5BaseUrl: "/origins-phase5", token: "secret" });
    await api.health();
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/origins-phase5/v1/health");
    expect(new Headers((init as RequestInit | undefined)?.headers).has("authorization")).toBe(false);
  });

  it("submits only path plus explicit approval for Oracle retrieval", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ owner: "oracle" }, 201));
    const api = new Phase5Api({ originsBaseUrl: "/origins-api", phase5BaseUrl: "/origins-phase5", token: "secret" });
    await api.retrieveRemoteFile("/safe/file.bin", true);
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/origins-phase5/v1/oracle/files/retrieve");
    expect(new Headers((init as RequestInit).headers).get("authorization")).toBe("Bearer secret");
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ remote_path: "/safe/file.bin", approved: true });
  });

  it("cannot supply executable argv or cwd when launching a registered application", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ accepted: true }, 202));
    const api = new Phase5Api({ originsBaseUrl: "/origins-api", phase5BaseUrl: "/origins-phase5", token: "secret" });
    await api.launchApplication("builder", "workspace-1", "c30fca67-0a93-4f94-bdec-176b4e55ec34");
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/origins-api/v1/applications/builder/launch");
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({
      workspace_id: "workspace-1",
      launch_id: "c30fca67-0a93-4f94-bdec-176b4e55ec34",
    });
  });

  it("promotes an Artifact only through the native registration contract", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ registered: true }, 201));
    const api = new Phase5Api({ originsBaseUrl: "/origins-api", phase5BaseUrl: "/origins-phase5", token: "secret" });
    await api.registerArtifact({
      workspace_id: "workspace-1",
      owner: "oracle",
      owner_ref: "stream-1",
      path: "/approved/root/result.bin",
      filename: "result.bin",
      media_type: "application/octet-stream",
    });
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/origins-api/v1/artifacts");
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({
      workspace_id: "workspace-1",
      owner: "oracle",
      owner_ref: "stream-1",
      path: "/approved/root/result.bin",
      filename: "result.bin",
      media_type: "application/octet-stream",
    });
  });
});
