export type ConnectionState = "disconnected" | "connecting" | "connected" | "degraded";

export type JsonRecord = Record<string, unknown>;

export interface HealthSnapshot extends JsonRecord {
  ok?: boolean;
  service?: string;
  api_version?: string;
  started_at?: string;
  workspaces?: number;
  repositories?: number;
  sessions?: number;
  capabilities?: number;
  journal?: JsonRecord;
}

export interface RepositorySnapshot extends JsonRecord {
  repository_id?: string;
  id?: string;
  workspace_id?: string;
  path?: string;
  root?: string;
  branch?: string;
  head?: string;
  dirty?: boolean;
}

export interface SessionSnapshot extends JsonRecord {
  session_id?: string;
  id?: string;
  workspace_id?: string;
  state?: string;
  status?: string;
  capability_id?: string;
  created_at?: string;
}

export interface HunterStatus extends JsonRecord {
  configured?: boolean;
  available?: boolean;
  base_origin?: string;
}

export function connectionStateFor(health: HealthSnapshot | null, authenticated: boolean): ConnectionState {
  if (!health) return "disconnected";
  if (health.ok !== true) return "degraded";
  return authenticated ? "connected" : "degraded";
}

export function safeText(value: unknown, fallback = "—"): string {
  if (typeof value === "string") return value || fallback;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

export function recordId(value: JsonRecord, ...keys: string[]): string {
  for (const key of keys) {
    const candidate = value[key];
    if (typeof candidate === "string" && candidate) return candidate;
  }
  return "unknown";
}

export function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2);
}
