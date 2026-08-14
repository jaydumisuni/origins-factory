import type { HealthSnapshot, HunterStatus, JsonRecord, RepositorySnapshot, SessionSnapshot } from "./model";

export class OriginsApiError extends Error {
  constructor(public readonly status: number, message: string, public readonly body?: unknown) {
    super(message);
    this.name = "OriginsApiError";
  }
}

export interface OriginsApiOptions {
  baseUrl: string;
  token: string;
}

export class OriginsApi {
  readonly baseUrl: string;
  private readonly token: string;

  constructor(options: OriginsApiOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.token = options.token.trim();
  }

  private async request<T>(path: string, init: RequestInit = {}, authenticated = true): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("accept", "application/json");
    if (init.body) headers.set("content-type", "application/json");
    if (authenticated) {
      if (!this.token) throw new OriginsApiError(401, "Local originsd token is required for this surface.");
      headers.set("authorization", `Bearer ${this.token}`);
    }
    const response = await fetch(`${this.baseUrl}${path}`, { ...init, headers });
    const text = await response.text();
    let body: unknown = null;
    if (text) {
      try { body = JSON.parse(text); } catch { body = text; }
    }
    if (!response.ok) {
      const detail = typeof body === "object" && body !== null && "message" in body
        ? String((body as JsonRecord).message)
        : `${response.status} ${response.statusText}`;
      throw new OriginsApiError(response.status, detail, body);
    }
    return body as T;
  }

  health(): Promise<HealthSnapshot> {
    return this.request<HealthSnapshot>("/v1/health", {}, false);
  }

  capabilities(): Promise<{ capabilities: JsonRecord[] }> {
    return this.request("/v1/capabilities");
  }

  repositories(workspaceId?: string): Promise<{ repositories: RepositorySnapshot[] }> {
    const query = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : "";
    return this.request(`/v1/repositories${query}`);
  }

  inspectRepository(workspaceId: string, path: string): Promise<RepositorySnapshot> {
    return this.request("/v1/repositories/inspect", {
      method: "POST",
      body: JSON.stringify({ workspace_id: workspaceId, path }),
    });
  }

  repositoryDiff(repositoryId: string, kind = "unstaged"): Promise<JsonRecord> {
    return this.request(`/v1/repositories/${encodeURIComponent(repositoryId)}/diff?kind=${encodeURIComponent(kind)}`);
  }

  sessions(): Promise<{ sessions: SessionSnapshot[] }> {
    return this.request("/v1/sessions");
  }

  sessionOutput(sessionId: string): Promise<JsonRecord> {
    return this.request(`/v1/sessions/${encodeURIComponent(sessionId)}/output`);
  }

  cancelSession(sessionId: string): Promise<JsonRecord> {
    return this.request(`/v1/sessions/${encodeURIComponent(sessionId)}/cancel`, { method: "POST" });
  }

  runCommand(envelope: JsonRecord): Promise<JsonRecord> {
    return this.request("/v1/commands", { method: "POST", body: JSON.stringify(envelope) });
  }

  events(afterSequence = 0, limit = 100): Promise<JsonRecord> {
    return this.request(`/v1/events?after_sequence=${afterSequence}&limit=${limit}`);
  }

  hunterStatus(): Promise<HunterStatus> {
    return this.request("/v1/hunter/status");
  }

  hunterRequest(workspaceId: string, operation: string, payload: unknown): Promise<JsonRecord> {
    return this.request("/v1/hunter/request", {
      method: "POST",
      body: JSON.stringify({ workspace_id: workspaceId, operation, payload }),
    });
  }
}

export const DEFAULT_API_BASE = "/origins-api";
