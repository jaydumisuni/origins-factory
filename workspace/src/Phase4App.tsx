import { FormEvent, useMemo, useState } from "react";
import { DEFAULT_API_BASE, OriginsApi } from "./api";
import HunterConversation from "./HunterConversation";
import ProcessTerminal from "./ProcessTerminal";
import RepositoryEditor from "./RepositoryEditor";
import {
  IntelligenceApi,
  type IntelligenceHealth,
  type OperationsSnapshot,
  type PlaybookSnapshot,
  type ProviderSnapshot,
} from "./intelligenceApi";
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

type View = "Factory" | "Workspace" | "Hunter" | "Operations" | "Armoury" | "Evidence" | "Sergeant" | "Recovery";
const views: View[] = ["Factory", "Workspace", "Hunter", "Operations", "Armoury", "Evidence", "Sergeant", "Recovery"];

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

function stringValue(record: JsonRecord, key: string, fallback = ""): string {
  const value = record[key];
  return typeof value === "string" ? value : fallback;
}

function nestedRecord(record: JsonRecord, key: string): JsonRecord | null {
  const value = record[key];
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as JsonRecord : null;
}

export default function Phase4App() {
  const [view, setView] = useState<View>("Factory");
  const [baseUrl, setBaseUrl] = useState(DEFAULT_API_BASE);
  const [token, setToken] = useState("");
  const [health, setHealth] = useState<HealthSnapshot | null>(null);
  const [authenticated, setAuthenticated] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [semanticError, setSemanticError] = useState("");
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

  const [intelligenceHealth, setIntelligenceHealth] = useState<IntelligenceHealth | null>(null);
  const [operations, setOperations] = useState<OperationsSnapshot | null>(null);
  const [playbooks, setPlaybooks] = useState<PlaybookSnapshot | null>(null);
  const [providers, setProviders] = useState<ProviderSnapshot | null>(null);
  const [pendingApprovals, setPendingApprovals] = useState<JsonRecord[]>([]);
  const [approvalResult, setApprovalResult] = useState<JsonRecord | null>(null);
  const [operationResult, setOperationResult] = useState<JsonRecord | null>(null);
  const [engineeringResult, setEngineeringResult] = useState<JsonRecord | null>(null);
  const [capabilityResult, setCapabilityResult] = useState<JsonRecord | null>(null);

  const [missionTitle, setMissionTitle] = useState("");
  const [missionTarget, setMissionTarget] = useState("");
  const [missionAction, setMissionAction] = useState("review_and_prepare");
  const [missionRisk, setMissionRisk] = useState("medium");
  const [missionPlaybook, setMissionPlaybook] = useState("code_ops");
  const [approvalId, setApprovalId] = useState("");
  const [engineeringOperationId, setEngineeringOperationId] = useState("");
  const [engineeringRepositoryId, setEngineeringRepositoryId] = useState("");
  const [engineeringTask, setEngineeringTask] = useState("");
  const [engineeringProvider, setEngineeringProvider] = useState("");
  const [capabilityWorkspace, setCapabilityWorkspace] = useState("");
  const [capabilityId, setCapabilityId] = useState("");
  const [capabilityReason, setCapabilityReason] = useState("");
  const [capabilityBenefit, setCapabilityBenefit] = useState("");

  const api = useMemo(() => new OriginsApi({ baseUrl, token }), [baseUrl, token]);
  const intelligence = useMemo(() => new IntelligenceApi(undefined, token), [token]);
  const connection = connectionStateFor(health, authenticated);
  const workspaceIds = useMemo(
    () => [...new Set([
      ...knownWorkspaceIds,
      ...repositories.map((repository) => repository.workspace_id ?? "").filter(Boolean),
    ])],
    [knownWorkspaceIds, repositories],
  );
  const semanticOperations = operations?.operations ?? [];
  const semanticProviders = providers?.providers ?? [];
  const semanticPlaybooks = playbooks?.playbooks ?? [];

  async function loadNative(): Promise<void> {
    const [repoPage, sessionPage, capabilityPage, eventPage, hunterStatus] = await Promise.all([
      api.repositories(), api.sessions(), api.capabilities(), api.events(), api.hunterStatus(),
    ]);
    setRepositories(repoPage.repositories ?? []);
    setSessions(sessionPage.sessions ?? []);
    setCapabilities(capabilityPage.capabilities ?? []);
    setEvents(asRecords(eventPage.events));
    setHunter(hunterStatus);
  }

  async function loadIntelligence(): Promise<void> {
    try {
      const [ownerHealth, operationPage, playbookPage, providerPage, approvalPage] = await Promise.all([
        intelligence.health(),
        intelligence.operations(),
        intelligence.playbooks(),
        intelligence.providers(),
        intelligence.approvals(),
      ]);
      setIntelligenceHealth(ownerHealth);
      setOperations(operationPage);
      setPlaybooks(playbookPage);
      setProviders(providerPage);
      setPendingApprovals(approvalPage.pending ?? []);
      setSemanticError("");
    } catch (cause) {
      setSemanticError(cause instanceof Error ? cause.message : String(cause));
    }
  }

  async function connect() {
    setBusy(true); setError(""); setSemanticError("");
    try {
      const nextHealth = await api.health();
      setHealth(nextHealth);
      setIntelligenceHealth(await intelligence.health().catch(() => null));
      if (!token.trim()) {
        setAuthenticated(false);
        setError("originsd is reachable. Enter the local bearer token to unlock protected projections.");
        return;
      }
      await loadNative();
      setAuthenticated(true);
      await loadIntelligence();
    } catch (cause) {
      setAuthenticated(false);
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  }

  function disconnect() {
    setHealth(null); setAuthenticated(false); setToken(""); setError(""); setSemanticError("");
    setRepositories([]); setSessions([]); setCapabilities([]); setEvents([]); setHunter(null);
    setSelectedRepository(""); setSelectedSession(""); setDiff(null); setSessionOutput(null);
    setIntelligenceHealth(null); setOperations(null); setPlaybooks(null); setProviders(null); setPendingApprovals([]);
    setApprovalResult(null); setOperationResult(null); setEngineeringResult(null); setCapabilityResult(null);
  }

  async function refresh() {
    if (!authenticated) return;
    setBusy(true); setError("");
    try {
      setHealth(await api.health());
      await loadNative();
      await loadIntelligence();
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
      setInspectWorkspace(workspaceId); setCapabilityWorkspace(workspaceId); setWorkspaceName("");
      setHealth(await api.health());
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  }

  async function inspectRepository(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const repository = await api.inspectRepository(inspectWorkspace.trim(), inspectPath.trim());
      const repositoryId = recordId(repository, "repository_id", "id");
      setSelectedRepository(repositoryId); setEngineeringRepositoryId(repositoryId);
      setKnownWorkspaceIds((current) => [...new Set([...current, inspectWorkspace.trim()])]);
      setRepositories((current) => [
        ...current.filter((item) => recordId(item, "repository_id", "id") !== repositoryId),
        repository,
      ]);
      setDiff(await api.repositoryDiff(repositoryId));
      setHealth(await api.health());
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  }

  async function loadDiff(repositoryId: string) {
    if (!repositoryId) return;
    setSelectedRepository(repositoryId); setEngineeringRepositoryId(repositoryId); setBusy(true); setError("");
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
    try { await api.cancelSession(sessionId); await loadNative(); setSessionOutput(await api.sessionOutput(sessionId)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  }

  async function requestOperationApproval(event: FormEvent) {
    event.preventDefault(); setBusy(true); setSemanticError("");
    try {
      const result = await intelligence.createApproval({
        kind: "operation",
        reason: `Review exact ${missionPlaybook} Operation before AgentOps admission.`,
        subject: {
          playbook: missionPlaybook,
          title: missionTitle.trim(),
          target: missionTarget.trim(),
          requested_action: missionAction.trim(),
          risk: missionRisk,
          evidence: {},
        },
      });
      setApprovalResult(result);
      const approval = nestedRecord(result, "approval");
      const request = approval ? nestedRecord(approval, "request") : null;
      const id = request ? stringValue(request, "approval_id") : "";
      setApprovalId(id);
      const prepared = nestedRecord(result, "prepared_operation");
      if (prepared) setEngineeringOperationId(stringValue(prepared, "operation_id"));
      await loadIntelligence();
    } catch (cause) { setSemanticError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  }

  async function decideApproval(decision: "approved" | "rejected") {
    if (!approvalId) return;
    setBusy(true); setSemanticError("");
    try {
      const result = await intelligence.decideApproval({
        approval_id: approvalId,
        decision,
        decided_by: "owner",
      });
      setApprovalResult(result);
      await loadIntelligence();
    } catch (cause) { setSemanticError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  }

  async function executeApprovedOperation() {
    if (!approvalId) return;
    setBusy(true); setSemanticError("");
    try {
      const result = await intelligence.runOperation({ approval_id: approvalId });
      setOperationResult(result);
      setEngineeringOperationId(stringValue(result, "operation_id", engineeringOperationId));
      await loadIntelligence();
    } catch (cause) { setSemanticError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  }

  async function runEngineeringAttempt(event: FormEvent) {
    event.preventDefault(); setBusy(true); setSemanticError("");
    try {
      const result = await intelligence.engineeringAttempt({
        operation_id: engineeringOperationId.trim(),
        repository_id: engineeringRepositoryId.trim(),
        task: engineeringTask.trim(),
        provider_id: engineeringProvider.trim(),
        apply_plan: false,
        review: "required",
        review_mode: "pull_request",
      });
      setEngineeringResult(result);
      await loadIntelligence();
    } catch (cause) { setSemanticError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  }

  async function compileCapability(event: FormEvent) {
    event.preventDefault(); setBusy(true); setSemanticError("");
    try {
      setCapabilityResult(await intelligence.compileCapability({
        workspace_id: capabilityWorkspace.trim(),
        task_title: `Capability proposal: ${capabilityId.trim()}`,
        capability_id: capabilityId.trim(),
        reason: capabilityReason.trim(),
        expected_benefit: capabilityBenefit.trim(),
        requested_effects: [],
        filesystem_read_scope: [],
        filesystem_write_scope: [],
        network_mode: "deny",
        network_hosts: [],
        environment_names: [],
        persistent_lease: false,
        delegated_remote_authority: false,
        alternatives: [],
        risks: [],
        requested_by: "owner",
      }));
    } catch (cause) { setSemanticError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  }

  const journal = health?.journal as JsonRecord | undefined;
  const activeRepository = repositories.find((repository) => recordId(repository, "repository_id", "id") === selectedRepository);
  const sergeantVerdict = engineeringResult ? stringValue(engineeringResult, "verdict") : "";
  const sergeantSummary = engineeringResult ? stringValue(engineeringResult, "summary") : "";

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
      <p>Native and semantic runtimes reconnect independently. Optional intelligence failure never disables native Factory work.</p>
    </section>

    <ErrorBanner message={error} />
    {semanticError && <div className="banner warn">Intelligence plane: {semanticError}</div>}
    <div className="shell">
      <nav>{views.map((item) => <button key={item} className={view === item ? "active" : ""} onClick={() => setView(item)}>{item}</button>)}</nav>
      <main>
        {view === "Factory" && <section>
          <h2>Factory</h2><p className="lead">Native mechanical truth plus separately mounted semantic owners.</p>
          <div className="metrics">
            <article><strong>{health?.workspaces ?? "—"}</strong><span>Workspaces</span></article>
            <article><strong>{health?.repositories ?? "—"}</strong><span>Repositories</span></article>
            <article><strong>{semanticOperations.length}</strong><span>AgentOps Operations</span></article>
            <article><strong>{semanticProviders.length}</strong><span>CodeOps Providers</span></article>
          </div>
          <div className="grid two">
            <article className="card"><h3>Native runtime</h3>{health ? <JsonPanel value={health} /> : <Empty>Connect to originsd to recover durable state.</Empty>}</article>
            <article className="card"><h3>Intelligence owners</h3>{intelligenceHealth ? <JsonPanel value={intelligenceHealth} /> : <Empty>Semantic owner plane is not reachable.</Empty>}</article>
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

        {view === "Hunter" && <section><h2>Hunter</h2><p className="lead">Hunter conversation remains optional intelligence; mechanical state remains native.</p>
          {!authenticated ? <Empty>Authenticate to inspect Hunter mounting.</Empty> : <>
            <article className="card"><h3>Hunter transport</h3>{hunter ? <JsonPanel value={hunter} /> : <Empty>Status not loaded.</Empty>}</article>
            <article className="card"><h3>Conversation</h3><HunterConversation api={api} configured={hunter?.configured === true} workspaceIds={workspaceIds} /></article>
          </>}
        </section>}

        {view === "Operations" && <section><h2>Operations</h2><p className="lead">AgentOps owns durable identity, approval, lifecycle and recovery. Origins projects and submits exact owner-bound packets.</p>
          <div className="grid two">
            <article className="card"><h3>Prepare Operation approval</h3><form onSubmit={requestOperationApproval}>
              <select value={missionPlaybook} onChange={(event) => setMissionPlaybook(event.target.value)}>{semanticPlaybooks.length ? semanticPlaybooks.map((playbook) => <option key={stringValue(playbook, "id")} value={stringValue(playbook, "id")}>{stringValue(playbook, "name", stringValue(playbook, "id"))}</option>) : <option value="code_ops">code_ops</option>}</select>
              <input value={missionTitle} onChange={(event) => setMissionTitle(event.target.value)} placeholder="Mission title" required />
              <input value={missionTarget} onChange={(event) => setMissionTarget(event.target.value)} placeholder="Repository / target" required />
              <input value={missionAction} onChange={(event) => setMissionAction(event.target.value)} placeholder="Requested semantic action" required />
              <select value={missionRisk} onChange={(event) => setMissionRisk(event.target.value)}><option>low</option><option>medium</option><option>high</option><option>critical</option></select>
              <button disabled={busy}>Create exact approval request</button>
            </form>{approvalResult && <JsonPanel value={approvalResult} />}</article>
            <article className="card"><h3>Approval → durable admission</h3><input value={approvalId} onChange={(event) => setApprovalId(event.target.value)} placeholder="AgentOps approval id" />
              <div className="action-row"><button disabled={busy || !approvalId} onClick={() => void decideApproval("approved")}>Approve</button><button className="secondary" disabled={busy || !approvalId} onClick={() => void decideApproval("rejected")}>Reject</button><button disabled={busy || !approvalId} onClick={() => void executeApprovedOperation()}>Submit approved Operation</button></div>
              {operationResult ? <JsonPanel value={operationResult} /> : <p className="muted">Execution submits only approval/proof references. The approved semantic packet cannot be rewritten here.</p>}
            </article>
          </div>
          <div className="grid two"><article className="card"><h3>Durable Operations</h3>{semanticOperations.length ? semanticOperations.map((operation, index) => <button className="row" key={stringValue(operation, "operation_id", String(index))} onClick={() => setEngineeringOperationId(stringValue(operation, "operation_id"))}><b>{stringValue(operation, "operation_id", "unknown")}</b><span>{stringValue(operation, "status", "unknown")} · dispatched={String(operation.execution_dispatched === true)}</span></button>) : <Empty>No durable AgentOps Operation results.</Empty>}</article><article className="card"><h3>Pending approvals</h3>{pendingApprovals.length ? pendingApprovals.map((approval, index) => <JsonPanel key={index} value={approval} />) : <Empty>No pending AgentOps approvals.</Empty>}</article></div>
          <article className="card"><h3>CodeOps mission + Sergeant proof</h3><form onSubmit={runEngineeringAttempt}>
            <div className="inline-form"><input value={engineeringOperationId} onChange={(event) => setEngineeringOperationId(event.target.value)} placeholder="operation id" required /><input value={engineeringRepositoryId} onChange={(event) => setEngineeringRepositoryId(event.target.value)} placeholder="repository id" required /><button disabled={busy}>Route + review</button></div>
            <input value={engineeringTask} onChange={(event) => setEngineeringTask(event.target.value)} placeholder="Engineering task" required />
            <select value={engineeringProvider} onChange={(event) => setEngineeringProvider(event.target.value)}><option value="">Owner router chooses provider</option>{semanticProviders.map((provider) => <option key={stringValue(provider, "id")} value={stringValue(provider, "id")}>{stringValue(provider, "id")} · {stringValue(provider, "model")}</option>)}</select>
          </form>{engineeringResult && <JsonPanel value={engineeringResult} />}</article>
        </section>}

        {view === "Armoury" && <section><h2>Armoury</h2><p className="lead">Native capability manifests plus CodeOps provider truth and approval-gated capability compilation.</p>
          <div className="grid two"><article className="card"><h3>CodeOps providers</h3>{semanticProviders.length ? semanticProviders.map((provider, index) => <div className="truth" key={stringValue(provider, "id", String(index))}><b>{stringValue(provider, "id", "unknown")}</b><span>{stringValue(provider, "model", "no model")} · {provider.enabled === true ? "enabled" : "disabled"} · credential={provider.credential_present === true ? "present" : "absent"}</span></div>) : <Empty>No provider registry available.</Empty>}</article><article className="card"><h3>Compile capability proposal</h3><form onSubmit={compileCapability}><input value={capabilityWorkspace} onChange={(event) => setCapabilityWorkspace(event.target.value)} placeholder="workspace id" required /><input value={capabilityId} onChange={(event) => setCapabilityId(event.target.value)} placeholder="capability id" required /><input value={capabilityReason} onChange={(event) => setCapabilityReason(event.target.value)} placeholder="reason" required /><input value={capabilityBenefit} onChange={(event) => setCapabilityBenefit(event.target.value)} placeholder="expected benefit" required /><button disabled={busy}>Compile proposal — do not activate</button></form>{capabilityResult && <JsonPanel value={capabilityResult} />}</article></div>
          {capabilities.length ? <div className="cards">{capabilities.map((item, index) => <article className="card" key={recordId(item, "capability_id", "id") + index}><h3>{recordId(item, "capability_id", "id")}</h3><JsonPanel value={item}/></article>)}</div> : <Empty>Connect and authenticate to load native capability manifests.</Empty>}
        </section>}

        {view === "Evidence" && <section><h2>Evidence</h2><p className="lead">Native append-only journal plus AgentOps semantic evidence. Raw process output remains with originsd Sessions.</p><div className="grid two"><article className="card"><h3>Native journal</h3>{events.length ? <div className="event-list">{events.map((item, index) => <JsonPanel key={index} value={item}/>)}</div> : <Empty>No native journal events loaded.</Empty>}</article><article className="card"><h3>AgentOps evidence</h3>{operations?.evidence?.length ? operations.evidence.map((item, index) => <JsonPanel key={index} value={item}/>) : <Empty>No semantic evidence loaded.</Empty>}</article></div></section>}

        {view === "Sergeant" && <section><h2>Sergeant</h2><p className="lead">Independent verdict ownership is preserved; Origins only projects the result of an assurance attempt.</p>{engineeringResult ? <div className="grid two"><article className="card"><h3>Latest verdict</h3><strong className="big">{sergeantVerdict || "—"}</strong><p className="muted">{sergeantSummary || "No summary returned."}</p></article><article className="card"><h3>Assurance record</h3><JsonPanel value={engineeringResult} /></article></div> : <div className="banner warn embedded">No Sergeant verdict has been requested in this client session. No PASS/FAIL is manufactured.</div>}</section>}

        {view === "Recovery" && <section><h2>Recovery</h2><p className="lead">Native Sessions and AgentOps Operations are recovered from their owning stores, not browser memory.</p><div className="metrics"><article><strong>{sessions.length}</strong><span>Native Sessions</span></article><article><strong>{repositories.length}</strong><span>Repositories</span></article><article><strong>{semanticOperations.length}</strong><span>Durable Operations</span></article><article><strong>{pendingApprovals.length}</strong><span>Pending approvals</span></article></div><div className="grid two"><article className="card"><h3>Journal integrity</h3>{journal ? <JsonPanel value={journal}/> : <Empty>Connect to read native journal integrity.</Empty>}</article><article className="card"><h3>AgentOps operation ledger</h3>{operations?.operation_ledger ? <JsonPanel value={operations.operation_ledger} /> : <Empty>Semantic recovery ledger unavailable.</Empty>}</article></div></section>}
      </main>
    </div>
  </div>;
}
