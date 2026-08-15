import type { JsonRecord } from "./model";

export interface Phase5Health extends JsonRecord {
  ok?: boolean;
  service?: string;
  api_version?: string;
  oracle?: { available?: boolean };
  lumi?: { available?: boolean };
  oracle_remote?: { configured?: boolean };
}

export interface Phase5ApiOptions {
  originsBaseUrl: string;
  phase5BaseUrl: string;
  token: string;
}

export interface ArtifactRegistration {
  workspace_id: string;
  owner: string;
  owner_ref: string;
  path: string;
  filename?: string;
  media_type?: string;
}

export class Phase5ApiError extends Error {
  constructor(public readonly status: number, message: string, public readonly body?: unknown) {
    super(message);
    this.name = "Phase5ApiError";
  }
}

function normalizeBase(value: string): string {
  return value.trim().replace(/\/$/, "");
}

export class Phase5Api {
  readonly originsBaseUrl: string;
  readonly phase5BaseUrl: string;
  private readonly token: string;

  constructor(options: Phase5ApiOptions) {
    this.originsBaseUrl = normalizeBase(options.originsBaseUrl);
    this.phase5BaseUrl = normalizeBase(options.phase5BaseUrl);
    this.token = options.token.trim();
  }

  private async request<T>(base: string, path: string, init: RequestInit = {}, authenticated = true): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("accept", "application/json");
    if (init.body) headers.set("content-type", "application/json");
    if (authenticated) {
      if (!this.token) throw new Phase5ApiError(401, "Origins local bearer token is required for Phase 5 owner surfaces.");
      headers.set("authorization", `Bearer ${this.token}`);
    }
    const response = await fetch(`${base}${path}`, { ...init, headers });
    const text = await response.text();
    let body: unknown = null;
    if (text) {
      try { body = JSON.parse(text); } catch { body = text; }
    }
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      if (typeof body === "object" && body !== null) {
        const record = body as JsonRecord;
        if (typeof record.message === "string") detail = record.message;
        else if (typeof record.error === "string") detail = record.error;
      }
      throw new Phase5ApiError(response.status, detail, body);
    }
    return body as T;
  }

  health(): Promise<Phase5Health> {
    return this.request(this.phase5BaseUrl, "/v1/health", {}, false);
  }

  browser(): Promise<JsonRecord> {
    return this.request(this.phase5BaseUrl, "/v1/browser");
  }

  setBrowserAuthority(authority: "observe" | "assist" | "act", approved = false): Promise<JsonRecord> {
    return this.request(this.phase5BaseUrl, "/v1/browser/handoff", {
      method: "POST",
      body: JSON.stringify({ authority, approved }),
    });
  }

  humanTakeover(): Promise<JsonRecord> {
    return this.request(this.phase5BaseUrl, "/v1/browser/human-takeover", {
      method: "POST",
      body: "{}",
    });
  }

  remoteNode(): Promise<JsonRecord> {
    return this.request(this.phase5BaseUrl, "/v1/oracle/node");
  }

  retrieveRemoteFile(remotePath: string, approved: boolean): Promise<JsonRecord> {
    return this.request(this.phase5BaseUrl, "/v1/oracle/files/retrieve", {
      method: "POST",
      body: JSON.stringify({ remote_path: remotePath, approved }),
    });
  }

  lumi(): Promise<JsonRecord> {
    return this.request(this.phase5BaseUrl, "/v1/lumi");
  }

  lumiTask(taskId: string): Promise<JsonRecord> {
    return this.request(this.phase5BaseUrl, `/v1/lumi/tasks/${encodeURIComponent(taskId)}`);
  }

  queueLumiDownload(input: {
    url: string;
    filename?: string;
    queue_id?: string;
    priority?: number;
    start_paused?: boolean;
  }): Promise<JsonRecord> {
    return this.request(this.phase5BaseUrl, "/v1/lumi/downloads", {
      method: "POST",
      body: JSON.stringify(input),
    });
  }

  lumiArtifactCandidate(taskId: string): Promise<JsonRecord> {
    return this.request(this.phase5BaseUrl, `/v1/lumi/artifact-candidates/${encodeURIComponent(taskId)}`, {
      method: "POST",
      body: "{}",
    });
  }

  applications(): Promise<{ applications: JsonRecord[] }> {
    return this.request(this.originsBaseUrl, "/v1/applications");
  }

  launchApplication(applicationId: string, workspaceId: string, launchId: string): Promise<JsonRecord> {
    return this.request(this.originsBaseUrl, `/v1/applications/${encodeURIComponent(applicationId)}/launch`, {
      method: "POST",
      body: JSON.stringify({ workspace_id: workspaceId, launch_id: launchId }),
    });
  }

  applicationLaunch(launchId: string): Promise<JsonRecord> {
    return this.request(this.originsBaseUrl, `/v1/application-launches/${encodeURIComponent(launchId)}`);
  }

  artifacts(workspaceId = ""): Promise<{ artifacts: JsonRecord[] }> {
    const query = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : "";
    return this.request(this.originsBaseUrl, `/v1/artifacts${query}`);
  }

  registerArtifact(input: ArtifactRegistration): Promise<JsonRecord> {
    return this.request(this.originsBaseUrl, "/v1/artifacts", {
      method: "POST",
      body: JSON.stringify({
        workspace_id: input.workspace_id,
        owner: input.owner,
        owner_ref: input.owner_ref,
        path: input.path,
        filename: input.filename ?? "",
        media_type: input.media_type ?? "",
      }),
    });
  }

  artifact(artifactId: string): Promise<JsonRecord> {
    return this.request(this.originsBaseUrl, `/v1/artifacts/${encodeURIComponent(artifactId)}`);
  }

  async artifactContent(artifactId: string): Promise<Blob> {
    if (!this.token) throw new Phase5ApiError(401, "Origins local bearer token is required for Artifact content.");
    const response = await fetch(`${this.originsBaseUrl}/v1/artifacts/${encodeURIComponent(artifactId)}/content`, {
      headers: { authorization: `Bearer ${this.token}` },
    });
    if (!response.ok) throw new Phase5ApiError(response.status, `${response.status} ${response.statusText}`);
    return response.blob();
  }
}

export const DEFAULT_PHASE5_API_BASE = "/origins-phase5";
