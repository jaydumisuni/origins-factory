import type { JsonRecord } from "./model";

export interface IntelligenceHealth extends JsonRecord {
  ok?: boolean;
  service?: string;
  api_version?: string;
  owners?: Record<string, { configured?: boolean; available?: boolean }>;
  mechanical_originsd_configured?: boolean;
}

export interface OperationsSnapshot extends JsonRecord {
  owner?: string;
  operations?: JsonRecord[];
  approvals?: JsonRecord[];
  evidence?: JsonRecord[];
  audit?: JsonRecord[];
  lessons?: JsonRecord[];
}

export interface ApprovalSnapshot extends JsonRecord {
  owner?: string;
  pending?: JsonRecord[];
}

export interface ProviderSnapshot extends JsonRecord {
  owner?: string;
  default_review?: string;
  providers?: JsonRecord[];
}

export class IntelligenceApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly body?: unknown,
  ) {
    super(message);
    this.name = "IntelligenceApiError";
  }
}

export const DEFAULT_INTELLIGENCE_BASE = "/origins-intelligence";

export class IntelligenceApi {
  private readonly baseUrl: string;
  private readonly token: string;

  constructor(baseUrl = DEFAULT_INTELLIGENCE_BASE, token = "") {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.token = token.trim();
  }

  private async request<T>(path: string, init: RequestInit = {}, authenticated = true): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("accept", "application/json");
    if (init.body) headers.set("content-type", "application/json");
    if (authenticated) {
      if (!this.token) throw new IntelligenceApiError(401, "Origins local bearer token is required.");
      headers.set("authorization", `Bearer ${this.token}`);
    }

    const response = await fetch(`${this.baseUrl}${path}`, { ...init, headers });
    const text = await response.text();
    let body: unknown = null;
    if (text) {
      try { body = JSON.parse(text); } catch { body = text; }
    }
    if (!response.ok) {
      const record = typeof body === "object" && body !== null ? body as JsonRecord : null;
      const message = record && typeof record.error === "string"
        ? record.error
        : `${response.status} ${response.statusText}`;
      throw new IntelligenceApiError(response.status, message, body);
    }
    return body as T;
  }

  health(): Promise<IntelligenceHealth> {
    return this.request<IntelligenceHealth>("/v1/health", {}, false);
  }

  operations(): Promise<OperationsSnapshot> {
    return this.request<OperationsSnapshot>("/v1/operations");
  }

  approvals(): Promise<ApprovalSnapshot> {
    return this.request<ApprovalSnapshot>("/v1/approvals");
  }

  providers(): Promise<ProviderSnapshot> {
    return this.request<ProviderSnapshot>("/v1/providers");
  }

  runOperation(payload: JsonRecord): Promise<JsonRecord> {
    return this.request<JsonRecord>("/v1/operations", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  createApproval(payload: JsonRecord): Promise<JsonRecord> {
    return this.request<JsonRecord>("/v1/approvals", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  decideApproval(payload: JsonRecord): Promise<JsonRecord> {
    return this.request<JsonRecord>("/v1/approvals/decision", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  compileCapability(payload: JsonRecord): Promise<JsonRecord> {
    return this.request<JsonRecord>("/v1/capability-proposals", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  engineeringAttempt(payload: JsonRecord): Promise<JsonRecord> {
    return this.request<JsonRecord>("/v1/engineering/attempt", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }
}
