import { FormEvent, useEffect, useState } from "react";
import { pretty, recordId, safeText, type JsonRecord, type RepositorySnapshot, type SessionSnapshot } from "./model";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("accept", "application/json");
  if (init.body) headers.set("content-type", "application/json");
  const response = await fetch(`/origins-api${path}`, { ...init, headers, credentials: "same-origin" });
  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try { body = JSON.parse(text); } catch { body = text; }
  }
  if (!response.ok) {
    const record = typeof body === "object" && body !== null ? body as JsonRecord : null;
    throw new Error(typeof record?.message === "string" ? record.message : typeof record?.error === "string" ? record.error : `${response.status} ${response.statusText}`);
  }
  return body as T;
}

function JsonPanel({ value }: { value: unknown }) {
  return <pre className="json">{pretty(value)}</pre>;
}

export default function InstalledApp({ sessionReady }: { sessionReady: boolean }) {
  const [health, setHealth] = useState<JsonRecord | null>(null);
  const [capabilities, setCapabilities] = useState<JsonRecord[]>([]);
  const [repositories, setRepositories] = useState<RepositorySnapshot[]>([]);
  const [sessions, setSessions] = useState<SessionSnapshot[]>([]);
  const [events, setEvents] = useState<JsonRecord[]>([]);
  const [workspaceName, setWorkspaceName] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");
  const [repositoryPath, setRepositoryPath] = useState("");
  const [executable, setExecutable] = useState("");
  const [argsText, setArgsText] = useState("[]");
  const [repositoryId, setRepositoryId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function refresh(): Promise<void> {
    setBusy(true); setError("");
    try {
      const [nextHealth, capabilityPage, repositoryPage, sessionPage, eventPage] = await Promise.all([
        request<JsonRecord>("/v1/health"),
        request<{ capabilities: JsonRecord[] }>("/v1/capabilities"),
        request<{ repositories: RepositorySnapshot[] }>("/v1/repositories"),
        request<{ sessions: SessionSnapshot[] }>("/v1/sessions"),
        request<{ events?: JsonRecord[] }>("/v1/events?after_sequence=0&limit=100"),
      ]);
      setHealth(nextHealth);
      setCapabilities(capabilityPage.capabilities ?? []);
      setRepositories(repositoryPage.repositories ?? []);
      setSessions(sessionPage.sessions ?? []);
      setEvents(Array.isArray(eventPage.events) ? eventPage.events : []);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  }

  useEffect(() => { if (sessionReady) void refresh(); }, [sessionReady]);

  async function createWorkspace(event: FormEvent): Promise<void> {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const created = await request<JsonRecord>("/v1/workspaces", {
        method: "POST",
        body: JSON.stringify({ name: workspaceName.trim(), authority_refs: [], session_refs: [] }),
      });
      const id = recordId(created, "workspace_id", "id");
      setWorkspaceId(id === "unknown" ? "" : id);
      setWorkspaceName("");
      await refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); setBusy(false); }
  }

  async function inspectRepository(event: FormEvent): Promise<void> {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const repository = await request<RepositorySnapshot>("/v1/repositories/inspect", {
        method: "POST",
        body: JSON.stringify({ workspace_id: workspaceId.trim(), path: repositoryPath.trim() }),
      });
      setRepositoryId(recordId(repository, "repository_id", "id"));
      await refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); setBusy(false); }
  }

  async function runCommand(event: FormEvent): Promise<void> {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const active = repositories.find((repository) => recordId(repository, "repository_id", "id") === repositoryId);
      if (!active?.workspace_id || !active.worktree_root) throw new Error("Select an inspected repository before running a process.");
      const args = JSON.parse(argsText) as unknown;
      if (!Array.isArray(args) || args.some((value) => typeof value !== "string")) throw new Error("Arguments must be a JSON array of strings.");
      await request<JsonRecord>("/v1/commands", {
        method: "POST",
        body: JSON.stringify({
          contract_type: "command_envelope",
          schema_version: "1.0.0",
          command_id: crypto.randomUUID(),
          workspace_id: active.workspace_id,
          capability_id: "origins.process.run",
          effect: "execute",
          payload: {
            workspace_root: active.worktree_root,
            executable: executable.trim(),
            args,
            cwd: ".",
            timeout_seconds: 120,
            max_output_bytes: 1024 * 1024,
          },
          created_at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
        }),
      });
      await refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); setBusy(false); }
  }

  if (!sessionReady) {
    return <div className="app">
      <header className="topbar">
        <div><div className="eyebrow">THETECHGUY · INSTALLED ORIGINS</div><h1>Origins Factory</h1></div>
        <div className="status disconnected"><span />session unavailable</div>
      </header>
      <div className="banner error">Installed Origins is running, but this browser session is not authorized. Close this tab and relaunch Origins Factory to establish a new one-time local session.</div>
    </div>;
  }

  return <div className="app">
    <header className="topbar">
      <div><div className="eyebrow">THETECHGUY · INSTALLED ORIGINS</div><h1>Origins Factory</h1></div>
      <div className={`status ${health?.ok === true ? "connected" : "disconnected"}`}><span />{health?.ok === true ? "native core ready" : "recovering"}</div>
    </header>
    <section className="connection-panel">
      <button onClick={() => void refresh()} disabled={busy}>{busy ? "Refreshing…" : "Refresh native state"}</button>
      <p>Installed mode keeps the bearer token outside browser JavaScript. Optional Hunter/Oracle/Lumi/AgentOps services are separate mounts and do not block native Factory work.</p>
    </section>
    {error && <div className="banner error">{error}</div>}
    <div className="shell"><main>
      <section><h2>Factory</h2><p className="lead">Durable local Origins runtime with external state and no model dependency.</p>
        <div className="metrics">
          <article><strong>{safeText(health?.workspaces, "—")}</strong><span>Workspaces</span></article>
          <article><strong>{repositories.length}</strong><span>Repositories</span></article>
          <article><strong>{sessions.length}</strong><span>Sessions</span></article>
          <article><strong>{capabilities.length}</strong><span>Capabilities</span></article>
        </div>
        <div className="grid two">
          <article className="card"><h3>Create Workspace</h3><form className="inline-create" onSubmit={(event) => void createWorkspace(event)}><input value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} placeholder="Workspace name" required /><button disabled={busy}>Create</button></form><p className="muted">Active Workspace: {workspaceId || "none selected"}</p></article>
          <article className="card"><h3>Inspect repository</h3><form className="inline-form" onSubmit={(event) => void inspectRepository(event)}><input value={workspaceId} onChange={(event) => setWorkspaceId(event.target.value)} placeholder="workspace id" required /><input value={repositoryPath} onChange={(event) => setRepositoryPath(event.target.value)} placeholder="approved local repository path" required /><button disabled={busy}>Inspect</button></form></article>
        </div>
        <article className="card"><h3>Repositories</h3>{repositories.length ? repositories.map((repository) => {
          const id = recordId(repository, "repository_id", "id");
          return <button className={`row ${repositoryId === id ? "selected" : ""}`} key={id} onClick={() => setRepositoryId(id)}><b>{safeText(repository.worktree_root, id)}</b><span>{safeText(repository.branch, "detached/unborn")}</span></button>;
        }) : <div className="empty">No repositories registered.</div>}</article>
        <article className="card"><h3>Supervised native process</h3><form className="inline-form" onSubmit={(event) => void runCommand(event)}><input value={executable} onChange={(event) => setExecutable(event.target.value)} placeholder="executable" required /><input value={argsText} onChange={(event) => setArgsText(event.target.value)} placeholder='["--version"]' required /><button disabled={busy || !repositoryId || !executable.trim()}>Run</button></form><p className="muted">Arguments are sent as argv through Origins process policy; installed mode adds no shell parser or new execution authority.</p></article>
        <div className="grid two"><article className="card"><h3>Process sessions</h3><JsonPanel value={sessions} /></article><article className="card"><h3>Capabilities</h3><JsonPanel value={capabilities} /></article></div>
        <article className="card"><h3>Evidence</h3><JsonPanel value={events} /></article>
      </section>
    </main></div>
  </div>;
}
