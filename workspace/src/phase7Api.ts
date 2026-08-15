import type { JsonRecord } from "./model";

export interface Phase7Health extends JsonRecord {
  ok?: boolean;
  service?: string;
  phase?: number;
  runtime_authority_expansion?: boolean;
  model_self_approval?: boolean;
}

export class Phase7ApiError extends Error {
  constructor(public readonly status: number, message: string, public readonly body?: unknown) {
    super(message);
    this.name = "Phase7ApiError";
  }
}

function normalizeBase(value: string): string {
  return value.trim().replace(/\/$/, "");
}

export class Phase7Api {
  readonly baseUrl: string;
  private readonly token: string;

  constructor(options: { baseUrl: string; token: string }) {
    this.baseUrl = normalizeBase(options.baseUrl);
    this.token = options.token.trim();
  }

  private async request<T>(method: string, path: string, body?: JsonRecord, authenticated = true): Promise<T> {
    const headers = new Headers({ accept: "application/json" });
    if (authenticated) {
      if (!this.token) throw new Phase7ApiError(401, "Origins local bearer token is required for capability evolution.");
      headers.set("authorization", `Bearer ${this.token}`);
    }
    let payload: string | undefined;
    if (body !== undefined) {
      headers.set("content-type", "application/json");
      payload = JSON.stringify(body);
    }
    const response = await fetch(`${this.baseUrl}${path}`, { method, headers, body: payload });
    const raw = await response.text();
    let decoded: unknown = null;
    if (raw) {
      try { decoded = JSON.parse(raw); } catch { decoded = raw; }
    }
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      if (typeof decoded === "object" && decoded !== null) {
        const record = decoded as JsonRecord;
        if (typeof record.detail === "string") detail = record.detail;
        else if (typeof record.error === "string") detail = record.error;
      }
      throw new Phase7ApiError(response.status, detail, decoded);
    }
    return decoded as T;
  }

  health(): Promise<Phase7Health> {
    return this.request("GET", "/v1/health", undefined, false);
  }

  evolutions(): Promise<{ phase?: number; evolutions?: JsonRecord[] }> {
    return this.request("GET", "/v1/evolutions");
  }

  evolution(id: string): Promise<JsonRecord> {
    return this.request("GET", `/v1/evolutions/${encodeURIComponent(id)}`);
  }

  confirmGap(payload: JsonRecord): Promise<JsonRecord> {
    return this.request("POST", "/v1/evolutions/gap", payload);
  }

  createApproval(id: string): Promise<JsonRecord> {
    return this.request("POST", `/v1/evolutions/${encodeURIComponent(id)}/approval`, {});
  }

  decideApproval(id: string, payload: JsonRecord): Promise<JsonRecord> {
    return this.request("POST", `/v1/evolutions/${encodeURIComponent(id)}/approval/decision`, payload);
  }

  createChildOperation(id: string, approvalId: string): Promise<JsonRecord> {
    return this.request("POST", `/v1/evolutions/${encodeURIComponent(id)}/child-operation`, { approval_id: approvalId });
  }

  implementCandidate(id: string, payload: JsonRecord): Promise<JsonRecord> {
    return this.request("POST", `/v1/evolutions/${encodeURIComponent(id)}/candidate`, payload);
  }

  recordCanary(id: string, sessionId: string): Promise<JsonRecord> {
    return this.request("POST", `/v1/evolutions/${encodeURIComponent(id)}/canary`, { session_id: sessionId });
  }

  decide(id: string, decision: "promote" | "rollback", decidedBy: string): Promise<JsonRecord> {
    return this.request("POST", `/v1/evolutions/${encodeURIComponent(id)}/decision`, { decision, decided_by: decidedBy });
  }

  resume(id: string): Promise<JsonRecord> {
    return this.request("POST", `/v1/evolutions/${encodeURIComponent(id)}/resume`, {});
  }
}

export const DEFAULT_PHASE7_API_BASE = "/origins-phase7";
