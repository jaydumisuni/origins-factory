import { FormEvent, useMemo, useState } from "react";
import { DEFAULT_API_BASE, OriginsApi } from "./api";
import { connectionStateFor, pretty, recordId, safeText, type HealthSnapshot, type HunterStatus, type JsonRecord, type RepositorySnapshot, type SessionSnapshot } from "./model";

type View = "Factory" | "Workspace" | "Hunter" | "Armoury" | "Evidence" | "Sergeant" | "Recovery";
const views: View[] = ["Factory", "Workspace", "Hunter", "Armoury", "Evidence", "Sergeant", "Recovery"];

function asRecords(value: unknown): JsonRecord[] {
  return Array.isArray(value) ? value.filter((item): item is JsonRecord => typeof item === "object" && item !== null) : [];
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
  const [inspectWorkspace, setInspectWorkspace] = useState("");
  const [inspectPath, setInspectPath] = useState("");
  const [commandText, setCommandText] = useState("{\n  \"capability_id\": \"origins.process.run\",\n  \"payload\": {}\n}");
  const [commandResult, setCommandResult] = useState<JsonRecord | null>(null);
  const [hunterWorkspace, setHunterWorkspace] = useState("");
  const [hunterOperation, setHunterOperation] = useState("core_status");
  const [hunterPayload, setHunterPayload] = useState("{}");
  const [hunterResult, setHunterResult] = useState<JsonRecord | null>(null);

  const api = useMemo(() => new OriginsApi({ baseUrl, token }), [baseUrl, token]);
  const connection = connectionStateFor(health, authenticated);

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
      const [repoPage, sessionPage, capabilityPage, eventPage, hunterStatus] = await Promise.all([
        api.repositories(), api.sessions(), api.capabilities(), api.events(), api.hunterStatus(),
      ]);
      setRepositories(repoPage.repositories ?? []);
      setSessions(sessionPage.sessions ?? []);
      setCapabilities(capabilityPage.capabilities ?? []);
      setEvents(asRecords(eventPage.events));
      setHunter(hunterStatus);
      setAuthenticated(true);
    } catch (cause) {
      setAuthenticated(false);
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  }

  function disconnect() {
    setHealth(null); setAuthenticated(false); setToken(""); setError("");
    setRepositories([]); setSessions([]); setCapabilities([]); setEvents([]); setHunter(null);
  }

  async function refresh() {
    if (!authenticated) return;
    setBusy(true); setError("");
    try {
      const [nextHealth, repoPage, sessionPage, capabilityPage, eventPage, hunterStatus] = await Promise.all([
        api.health(), api.repositories(), api.sessions(), api.capabilities(), api.events(), api.hunterStatus(),
      ]);
      setHealth(nextHealth); setRepositories(repoPage.repositories ?? []); setSessions(sessionPage.sessions ?? []);
      setCapabilities(capabilityPage.capabilities ?? []); setEvents(asRecords(eventPage.events)); setHunter(hunterStatus);
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  }

  async function inspectRepository(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const repository = await api.inspectRepository(inspectWorkspace.trim(), inspectPath.trim());
      await refresh();
      setSelectedRepository(recordId(repository, "repository_id", "id"));
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); setBusy(false); }
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

  async function runCommand(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const parsed = JSON.parse(commandText) as JsonRecord;
      setCommandResult(await api.runCommand(parsed));
      await refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); setBusy(false); }
  }

  async function sendHunter(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const payload = JSON.parse(hunterPayload) as unknown;
      setHunterResult(await api.hunterRequest(hunterWorkspace.trim(), hunterOperation, payload));
      await refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); setBusy(false); }
  }

  const journal = health?.journal as JsonRecord | undefined;
  const sergeantEvents = events.filter((item) => JSON.stringify(item).toLowerCase().includes("sergeant") || JSON.stringify(item).toLowerCase().includes("assurance"));

  return <div className="app">
    <header className="topbar">
      <div><div className="eyebrow">THETECHGUY · MISSION OPERATING ENVIRONMENT</div><h1>Origins Factory</h1></div>
      <div className={`status ${connection}`}><span />{connection}</div>
    </header>

    <section className="connection-panel">
      <label>originsd endpoint<input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} disabled={busy || authenticated} /></label>
      <label>local bearer token<input type="password" value={token} onChange={(e) => setToken(e.target.value)} disabled={busy || authenticated} placeholder="kept in memory only" /></label>
      {!authenticated ? <button onClick={connect} disabled={busy}>{busy ? "Connecting…" : "Connect"}</button> : <><button onClick={refresh} disabled={busy}>Refresh</button><button className="secondary" onClick={disconnect}>Disconnect</button></>}
      <p>No background retry loop. Reconnect and refresh are explicit user actions.</p>
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
          <div className="grid two"><article className="card"><h3>Native runtime</h3>{health ? <JsonPanel value={health} /> : <Empty>Connect to originsd to recover durable state.</Empty>}</article>
          <article className="card"><h3>Authority boundary</h3><div className="truth"><b>Stage‑2 containment</b><span>Proven and merged</span></div><div className="truth warn"><b>Model/runtime activation</b><span>Not implied by this client</span></div><div className="truth warn"><b>Browser / MCP / endpoint broker</b><span>Unavailable until separately activated and proven</span></div></article></div>
        </section>}

        {view === "Workspace" && <section>
          <h2>Workspace</h2><p className="lead">Repository, diff, process-session and human command surfaces backed by originsd.</p>
          {!authenticated ? <Empty>Authenticate to load protected Workspace projections.</Empty> : <>
            <div className="grid two"><article className="card"><h3>Repositories</h3>
              <form className="inline-form" onSubmit={inspectRepository}><input value={inspectWorkspace} onChange={(e) => setInspectWorkspace(e.target.value)} placeholder="workspace id" required /><input value={inspectPath} onChange={(e) => setInspectPath(e.target.value)} placeholder="approved repository path" required /><button disabled={busy}>Inspect</button></form>
              {repositories.length ? repositories.map((repo) => { const id = recordId(repo, "repository_id", "id"); return <button className={`row ${selectedRepository === id ? "selected" : ""}`} key={id} onClick={() => loadDiff(id)}><b>{safeText(repo.path ?? repo.root, id)}</b><span>{safeText(repo.branch)} · {repo.dirty === true ? "dirty" : "clean/unknown"}</span></button>; }) : <Empty>No registered repositories.</Empty>}
            </article><article className="card"><h3>Repository diff</h3>{diff ? <JsonPanel value={diff} /> : <Empty>Select a repository to load its dedicated Git diff projection.</Empty>}</article></div>
            <div className="grid two"><article className="card"><h3>Process sessions</h3>{sessions.length ? sessions.map((session) => { const id = recordId(session, "session_id", "id"); return <button className={`row ${selectedSession === id ? "selected" : ""}`} key={id} onClick={() => loadSession(id)}><b>{id}</b><span>{safeText(session.state ?? session.status)} · {safeText(session.capability_id)}</span></button>; }) : <Empty>No durable process sessions.</Empty>}</article><article className="card"><h3>Terminal evidence</h3>{sessionOutput ? <JsonPanel value={sessionOutput} /> : <Empty>Select a session to recover retained stdout/stderr evidence.</Empty>}</article></div>
            <article className="card"><h3>Human-controlled command admission</h3><p className="muted">This surface forwards an explicit command envelope to existing originsd admission. It does not mint leases, bypass ProcessPolicy, or grant model authority.</p><form onSubmit={runCommand}><textarea value={commandText} onChange={(e) => setCommandText(e.target.value)} rows={10} spellCheck={false}/><button disabled={busy}>Submit exact envelope</button></form>{commandResult && <JsonPanel value={commandResult}/>}</article>
          </>}
        </section>}

        {view === "Hunter" && <section><h2>Hunter</h2><p className="lead">Optional intelligence transport. Mechanical state remains in originsd.</p>
          {!authenticated ? <Empty>Authenticate to inspect Hunter mounting.</Empty> : <><article className="card"><h3>Transport status</h3>{hunter ? <JsonPanel value={hunter}/> : <Empty>Status not loaded.</Empty>}</article>
          {hunter?.configured === true ? <article className="card"><h3>Bounded request</h3><form onSubmit={sendHunter}><input value={hunterWorkspace} onChange={(e) => setHunterWorkspace(e.target.value)} placeholder="workspace id" required/><select value={hunterOperation} onChange={(e) => setHunterOperation(e.target.value)}><option>version</option><option>session</option><option>core_status</option><option>providers_status</option><option>chat_list</option><option>chat_load</option><option>chat_save</option><option>core_chat</option></select><textarea value={hunterPayload} onChange={(e) => setHunterPayload(e.target.value)} rows={8}/><button disabled={busy}>Send through Origins transport</button></form>{hunterResult && <JsonPanel value={hunterResult}/>}</article> : <div className="banner warn">Hunter transport is not configured. The Factory stays usable; no fake chat fallback is shown.</div>}</>}
        </section>}

        {view === "Armoury" && <section><h2>Armoury</h2><p className="lead">Registered capabilities are shown as runtime truth, not promises.</p>{capabilities.length ? <div className="cards">{capabilities.map((item, index) => <article className="card" key={recordId(item, "capability_id", "id") + index}><h3>{recordId(item, "capability_id", "id")}</h3><JsonPanel value={item}/></article>)}</div> : <Empty>Connect and authenticate to load capability manifests.</Empty>}</section>}

        {view === "Evidence" && <section><h2>Evidence</h2><p className="lead">Append-only journal projection. Refresh is explicit.</p>{events.length ? <div className="event-list">{events.map((item, index) => <JsonPanel key={index} value={item}/>)}</div> : <Empty>No journal events loaded.</Empty>}</section>}

        {view === "Sergeant" && <section><h2>Sergeant</h2><p className="lead">Independent assurance must remain independent from implementation authority.</p>{sergeantEvents.length ? sergeantEvents.map((item, index) => <JsonPanel key={index} value={item}/>) : <div className="banner warn">No mounted Sergeant verdict stream is present in the current native API. The view remains explicitly unavailable rather than manufacturing PASS/FAIL.</div>}</section>}

        {view === "Recovery" && <section><h2>Recovery</h2><p className="lead">Reconnect to persisted native state after UI loss; durable work is not owned by this browser process.</p><div className="grid two"><article className="card"><h3>Journal integrity</h3>{journal ? <JsonPanel value={journal}/> : <Empty>Connect to read journal integrity.</Empty>}</article><article className="card"><h3>Recovered sessions</h3><strong className="big">{sessions.length}</strong><p className="muted">sessions currently projected by originsd</p></article></div><div className="banner warn">Cross-client restart/resume is projected from native state, but Windows/Linux desktop packaging remains a separate v1 completion gate.</div></section>}
      </main>
    </div>
  </div>;
}
