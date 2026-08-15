import type { JsonRecord } from "./model";

export interface Phase6Health extends JsonRecord {
  ok?: boolean;
  service?: string;
  api_version?: string;
  device_write_available?: boolean;
  huawei_gateway?: { available?: boolean };
  xray_bundle?: { configured?: boolean };
}

export class Phase6ApiError extends Error {
  constructor(public readonly status: number, message: string, public readonly body?: unknown) {
    super(message);
    this.name = "Phase6ApiError";
  }
}

function normalizeBase(value: string): string {
  return value.trim().replace(/\/$/, "");
}

export class Phase6Api {
  readonly baseUrl: string;
  private readonly token: string;

  constructor(options: { baseUrl: string; token: string }) {
    this.baseUrl = normalizeBase(options.baseUrl);
    this.token = options.token.trim();
  }

  private async request<T>(path: string, authenticated = true): Promise<T> {
    const headers = new Headers({ accept: "application/json" });
    if (authenticated) {
      if (!this.token) throw new Phase6ApiError(401, "Origins local bearer token is required for Phase 6 device projections.");
      headers.set("authorization", `Bearer ${this.token}`);
    }
    const response = await fetch(`${this.baseUrl}${path}`, { method: "GET", headers });
    const raw = await response.text();
    let body: unknown = null;
    if (raw) {
      try { body = JSON.parse(raw); } catch { body = raw; }
    }
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      if (typeof body === "object" && body !== null) {
        const record = body as JsonRecord;
        if (typeof record.message === "string") detail = record.message;
        else if (typeof record.error === "string") detail = record.error;
      }
      throw new Phase6ApiError(response.status, detail, body);
    }
    return body as T;
  }

  health(): Promise<Phase6Health> {
    return this.request("/v1/health", false);
  }

  device(): Promise<JsonRecord> {
    return this.request("/v1/device");
  }

  gateway(): Promise<JsonRecord> {
    return this.request("/v1/huawei/gateway");
  }

  xray(): Promise<JsonRecord> {
    return this.request("/v1/xray/bundle");
  }
}

export const DEFAULT_PHASE6_API_BASE = "/origins-phase6";
