import { FormEvent, useMemo, useState } from "react";
import { DEFAULT_API_BASE, OriginsApi } from "./api";
import HunterConversation from "./HunterConversation";
import ProcessTerminal from "./ProcessTerminal";
import RepositoryEditor from "./RepositoryEditor";
import {
  connectionStateFor,
  pretty,
  recordId,
  safeText,
  type HealthSnapshot,
  type HunterStatus,
  type JsonRecord,
  type RepositorySnapshot,
  type SessionSnapshot,
} from "./model";

type View = "Factory" | "Workspace" | "Hunter" | "Armoury" | "Evidence" | "Sergeant" | "Recovery";
const views: View[] = ["Factory", "Workspace", "Hunter", "Armoury", "Evidence", "Sergeant", "Recovery"];

function asRecords(value: unknown): JsonRecord[] {
  return Array.isArray(value)
    ? value.filter((item): item is JsonRecord => typeof item === "object" && item !== null)
    : [];
}

function ErrorBanner({ message }: { message: string }) {
  return message ? <div className="banner error">{message}</div> : null;
}

function Empty({ children }: { children: string }) {
  return <div className="empty">{children}</div>;
}

function JsonPanel({ value }: { value: unknown }) {
  return <pre className="json">{pretty(value)}</pre>;
}

function isDirty(repository: RepositorySnapshot): boolean {
  return (repository.staged_count ?? 0) + (repository.unstaged_count ?? 0) + (repository.untracked_count ?? 0) > 0;
}

export default function App() {
  const [view, setView] = useState<View>("Factory");
  const [baseUrl, setBaseUrl] = useState(DEFAULT_API_BASE);
  const [token, setToken] = useState("");
  const [health, setHealth] = useState<HealthSnapshot | null>(null);
  const [authenticated, setAuthenticated] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [repositories, setRepositories] = useState<RepositorySnapshot[]>([]);
  const [sessions, setSessions] = useState<SessionSnapshot[]>([]);
  const [capabilities, setCapabilities] = useState<JsonRecord[]>([]);
  const [events, setEvents] = useState<JsonRecord[]>([]);
  const [hunter, setHunter] = useState<HunterStatus | null>(null);
  const [selectedRepository, setSelectedRepository] = useState("");
  const [diff, setDiff] = useState<JsonRecord | null>(null);
  const [selectedSession, setSelectedSession] = useState("");
  const [sessionOutput, setSessionOutput] = useState<JsonRecord | null>(null);
  const [workspaceName, setWorkspaceName] = useState("");
  const [knownWorkspaceIds, setKnownWorkspaceIds] = useState<string[]>([]);
  const [inspectWorkspace, setInspectWorkspace] = useState("");
  const [inspectPath, setInspectPath] = useState("");

  const api = useMemo(() => new OriginsApi({ baseUrl, token }), [baseUrl, token]);
  const connection = connectionStateFor(health, authenticated);
  const workspaceIds = useMemo(
    () => [...new Set([
      ...knownWorkspaceIds,
      ...repositories.map((repository) => repository.workspace_id ?? "").filter(Boolean),
    ])],
    [knownWorkspaceIds, repositories],
  );

  async function loadProtected(): Promise<void> {
    const [repoPage, sessionPage, capabilityPage, eventPage, hunterStatus] = await Promise.all([
      api.repositories(), api.sessions(), api.capabilities(), api.events(), api.hunterStatus(),
    ]);
    setRepositories(repoPage.repositories ?? []);
    setSessions(sessionPage.sessions ?? []);
    setCapabilities(capabilityPage.capabilities ?? []);
    setEvents(asRecords(eventPage.events));
    setHunter(hunterStatus);
  }

  async function connect() {
    setBusy(true); setError("");
    try {
      const nextHealth = await api.health();
      setHealth(nextHealth);
      if (!token.trim()) {
        setAuthenticated(false);
        setError("originsd is reachable. Enter the local bearer token to unlock protected projections.");
        return;
      }
      await loadProtected();
      setAuthenticated(true);
    } catch (cause) {
      setAuthenticated(false);
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  }

  function disconnect() {
    setHealth(null); setAuthenticated(false); setToken(""); setError("");
    setRepositories([]); setSessions([]); setCapabilities([]); setEvents([]); setHunter(null);
    setSelectedRepository(""); setSelectedSession(""); setDiff(null); setSessionOutput(null);
  }

  async function refresh() {
    if (!authenticated) return;
    setBusy(true); setError("");
    try {
      setHealth(await api.health());
      await loadProtected();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  }

  async function createWorkspace(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const workspace = await api.createWorkspace(workspaceName.trim());
      const workspaceId = recordId(workspace, "workspace_id", "id");
      if (workspaceId === "unknown") throw new Error("originsd returned a Workspace without a canonical workspace_id.");
      setKnownWorkspaceIds((current) => [...new Set([...current, workspaceId])]);
      setInspectWorkspace(workspaceId);
      setWorkspaceName("");
      setHealth(await api.health());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  }

  async function inspectRepository(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const repository = await api.inspectRepository(inspectWorkspace.trim(), inspectPath.trim());
      const repositoryId = recordId(repository, "repository_id", "id");
      setSelectedRepository(repositoryId);
      setKnownWorkspaceIds((current) => [...new Set([...current, inspectWorkspace.trim()])]);
      setRepositories((current) => {
        const remaining = current.filter((item) => recordId(item, "repository_id", "id") !== repositoryId);
        return [...remaining, repository];
      });
      setDiff(await api.repositoryDiff(repositoryId));
      setHealth(await api.health());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  }

  async function loadDiff(repositoryId: string) {
    if (!repositoryId) return;
    setSelectedRepository(repositoryId); setBusy(true); setError("");
    try { setDiff(await api.repositoryDiff(repositoryId)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  }

  async function loadSession(sessionId: string) {
    if (!sessionId) return;
    setSelectedSession(sessionId); setBusy(true); setError("");
    try { setSessionOutput(await api.sessionOutput(sessionId)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  }

  async function cancelSession(sessionId: string) {
    setBusy(true); setError("");
    try {
      await api.cancelSession(sessionId);
      await loadProtected();
      setSessionOutput(await api.sessionOutput(sessionId));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  }

  const journal = health?.journal as JsonRecord | undefined;
  const sergeantEvents = events.filter((item) => {
    const value = JSON.stringify(item).toLowerCase();
    return value.includes("sergeant") || value.includes("assurance");
  });
  const activeRepository = repositories.find((repository) => recordId(repository, "repository_id", "id") === selectedRepository);

  return <div className="app">
    <header className="topbar">
      <div><div className="eyebrow">THETECHGUY · MISSION OPERATING ENVIRONMENT</div><h1>Origins Factory</h1></div>
      <div className={`status ${connection}`}><span />{connection}</div>
    </header>

    <section className="connection-panel">
      <label>originsd endpoint<input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} disabled={busy || authenticated} /></label>
      <label>local bearer token<input type="password" value={token} onChange={(event) => setToken(event.target.value)} disabled={busy || authenticated} placeholder="kept in memory only" /></label>
      {!authenticated
        ? <button onClick={() => void connect()} disabled={busy}>{busy ? "Connecting…" : "Connect"}</button>
        : <><button onClick={() => void refresh()} disabled={busy}>Refresh</button><button className="secondary" onClick={disconnect}>Disconnect</button></>}
      <p>No background retry loop. Reconnect and refresh are explicit user actions; durable state remains native.</p>
    </section>

    <ErrorBanner message={error} />
    <div className="shell">
      <nav>{views.map((item) => <button key={item} className={view === item ? "active" : ""} onClick={() => setView(item)}>{item}</button>)}</nav>
      <main>
        {view === "Factory" && <section>
          <h2>Factory</h2><p className="lead">Durable native truth, projected without pretending optional providers are active.</p>
          <div className="metrics">
            <article><strong>{health?.workspaces ?? "—"}</strong><span>Workspaces</span></article>
            <article><strong>{health?.repositories ?? "—"}</strong><span>Repositories</span></article>
            <article><strong>{health?.sessions ?? "—"}</strong><span>Sessions</span></article>
            <article><strong>{health?.capabilities ?? "—"}</strong><span>Capabilities</span></article>
          </div>
          <div className="grid two">
            <article className="card"><h3>Native runtime</h3>{health ? <JsonPanel value={health} /> : <Empty>Connect to originsd to recover durable state.</Empty>}</article>
            <article className="card"><h3>Authority boundary</h3>
              <div className="truth"><b>Stage‑2 containment</b><span>Proven and merged</span></div>
              <div className="truth"><b>Workspace shell</b><span>Bound to native v1 APIs</span></div>
              <div className="truth warn"><b>Model/runtime authority</b><span>Never implied by UI connection</span></div>
              <div className="truth warn"><b>Browser / remote / device write</b><span>Separate roadmap gates</span></div>
            </article>
          </div>
        </section>}

        {view === "Workspace" && <section>
          <h2>Workspace</h2><p className="lead">Repository, bounded editor, Git diff and supervised process surfaces backed by originsd.</p>
          {!authenticated ? <Empty>Authenticate to load protected Workspace projections.</Empty> : <>
            <div className="grid two">
              <article className="card"><h3>Create durable Workspace</h3><form className="inline-create" onSubmit={createWorkspace}><input value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} placeholder="Workspace name" required /><button disabled={busy || !workspaceName.trim()}>Create</button></form>{workspaceIds.length ? <p className="muted">Known this client session: {workspaceIds.join(", ")}</p> : <p className="muted">No Workspace ID has been recovered in this client yet.</p>}</article>
              <article className="card"><h3>Inspect repository</h3><form className="inline-form" onSubmit={inspectRepository}><input value={inspectWorkspace} onChange={(event) => setInspectWorkspace(event.target.value)} placeholder="workspace id" required /><input value={inspectPath} onChange={(event) => setInspectPath(event.target.value)} placeholder="approved repository path" required /><button disabled={busy}>Inspect</button></form></article>
            </div>

            <div className="grid two"><article className="card"><h3>Repositories</h3>
              {repositories.length ? repositories.map((repository) => {
                const id = recordId(repository, "repository_id", "id");
                const changes = (repository.staged_count ?? 0) + (repository.unstaged_count ?? 0) + (repository.untracked_count ?? 0);
                return <button className={`row ${selectedRepository === id ? "selected" : ""}`} key={id} onClick={() => void loadDiff(id)}><b>{safeText(repository.worktree_root, id)}</b><span>{safeText(repository.branch, "detached/unborn")} · {isDirty(repository) ? `${changes} changes` : "clean"}</span></button>;
              }) : <Empty>No registered repositories.</Empty>}
            </article><article className="card"><h3>Repository diff</h3>{diff ? <JsonPanel value={diff} /> : <Empty>Select a repository to load its dedicated Git diff projection.</Empty>}</article></div>

            <article className="card workspace-editor-card"><h3>Repository editor</h3>{activeRepository ? <RepositoryEditor api={api} repositoryId={recordId(activeRepository, "repository_id", "id")} /> : <Empty>Select a repository to browse and edit bounded UTF‑8 files.</Empty>}</article>

            <div className="grid two"><article className="card"><h3>Supervised process terminal</h3><ProcessTerminal api={api} repositories={repositories} onAccepted={refresh} /></article><article className="card"><h3>Process sessions</h3>{sessions.length ? sessions.map((session) => {
              const id = recordId(session, "session_id", "id");
              const active = session.state === "starting" || session.state === "running";
              return <div className="session-row" key={id}><button className={`row ${selectedSession === id ? "selected" : ""}`} onClick={() => void loadSession(id)}><b>{id}</b><span>{safeText(session.state ?? session.status)} · {safeText(session.capability_id)}</span></button>{active && <button className="danger-small" disabled={busy} onClick={() => void cancelSession(id)}>Cancel</button>}</div>;
            }) : <Empty>No durable process sessions.</Empty>}</article></div>
            <article className="card"><h3>Terminal evidence</h3>{sessionOutput ? <JsonPanel value={sessionOutput} /> : <Empty>Select a Session to recover retained stdout/stderr evidence.</Empty>}</article>
          </>}
        </section>}

        {view === "Hunter" && <section><h2>Hunter</h2><p className="lead">Conversation is transported through Origins; mechanical state remains native and optional intelligence failure does not disable Factory work.</p>
          {!authenticated ? <Empty>Authenticate to inspect Hunter mounting.</Empty> : <>
            <article className="card"><h3>Python intelligence transport</h3>{hunter ? <JsonPanel value={hunter} /> : <Empty>Status not loaded.</Empty>}</article>
            <article className="card"><h3>Hunter conversation</h3><HunterConversation api={api} configured={hunter?.configured === true} workspaceIds={workspaceIds} /></article>
          </>}
        </section>}

        {view === "Armoury" && <section><h2>Armoury</h2><p className="lead">Registered capabilities are runtime truth, not promises.</p>{capabilities.length ? <div className="cards">{capabilities.map((item, index) => <article className="card" key={recordId(item, "capability_id", "id") + index}><h3>{recordId(item, "capability_id", "id")}</h3><JsonPanel value={item}/></article>)}</div> : <Empty>Connect and authenticate to load capability manifests.</Empty>}</section>}

        {view === "Evidence" && <section><h2>Evidence</h2><p className="lead">Append-only native journal projection. Refresh is explicit.</p>{events.length ? <div className="event-list">{events.map((item, index) => <JsonPanel key={index} value={item}/>)}</div> : <Empty>No journal events loaded.</Empty>}</section>}

        {view === "Sergeant" && <section><h2>Sergeant</h2><p className="lead">Independent assurance must remain independent from implementation authority.</p>{sergeantEvents.length ? sergeantEvents.map((item, index) => <JsonPanel key={index} value={item}/>) : <div className="banner warn embedded">No mounted Sergeant verdict stream is present in the current native API. The view remains explicitly unavailable rather than manufacturing PASS/FAIL.</div>}</section>}

        {view === "Recovery" && <section><h2>Recovery</h2><p className="lead">Reconnect to persisted native state after UI loss; durable work is not owned by this browser process.</p><div className="grid two"><article className="card"><h3>Journal integrity</h3>{journal ? <JsonPanel value={journal}/> : <Empty>Connect to read journal integrity.</Empty>}</article><article className="card"><h3>Recovered native state</h3><strong className="big">{sessions.length}</strong><p className="muted">process Sessions currently projected by originsd</p><strong className="big smaller">{repositories.length}</strong><p className="muted">repository projections recovered</p></article></div><div className="banner warn embedded">Cross-client native reconnect is present. Windows/Linux desktop packaging and semantic Mission/Operation resume remain later completion gates.</div></section>}
      </main>
    </div>
  </div>;
}
