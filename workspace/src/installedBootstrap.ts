export interface InstalledSessionState {
  installedProxy: boolean;
  authenticated: boolean;
}

const DEVELOPMENT_STATE: InstalledSessionState = { installedProxy: false, authenticated: false };

function bootstrapNonce(): string {
  const fragment = window.location.hash.startsWith("#") ? window.location.hash.slice(1) : window.location.hash;
  const params = new URLSearchParams(fragment);
  return params.get("bootstrap")?.trim() ?? "";
}

function clearBootstrapFragment(): void {
  if (window.location.hash) {
    history.replaceState(null, document.title, `${window.location.pathname}${window.location.search}`);
  }
}

export function classifyInstalledSession(value: unknown, responseOk: boolean): InstalledSessionState {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return DEVELOPMENT_STATE;
  const record = value as Record<string, unknown>;
  if (record.installed_proxy !== true) return DEVELOPMENT_STATE;
  return {
    installedProxy: true,
    authenticated: responseOk && record.authenticated === true,
  };
}

async function classifyResponse(response: Response): Promise<InstalledSessionState> {
  let body: unknown = null;
  try { body = await response.json(); } catch { return DEVELOPMENT_STATE; }
  return classifyInstalledSession(body, response.ok);
}

export async function establishInstalledSession(): Promise<InstalledSessionState> {
  const nonce = bootstrapNonce();
  try {
    if (nonce) {
      const response = await fetch("/origins-bootstrap", {
        method: "POST",
        credentials: "same-origin",
        headers: { "content-type": "application/json", "accept": "application/json" },
        body: JSON.stringify({ nonce }),
      });
      clearBootstrapFragment();
      return await classifyResponse(response);
    }

    const response = await fetch("/origins-bootstrap/status", {
      method: "GET",
      credentials: "same-origin",
      headers: { "accept": "application/json" },
    });
    return await classifyResponse(response);
  } catch {
    return DEVELOPMENT_STATE;
  }
}
