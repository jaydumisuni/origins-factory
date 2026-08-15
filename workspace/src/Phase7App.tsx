import { useMemo, useState } from "react";
import Phase6App from "./Phase6App";
import { pretty, safeText, type JsonRecord } from "./model";
import { DEFAULT_PHASE7_API_BASE, Phase7Api, type Phase7Health } from "./phase7Api";
import "./phase7.css";

type Surface = "Workspace" | "EVOLUTION";

function asRecord(value: unknown): JsonRecord | null {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as JsonRecord : null;
}

function asRecords(value: unknown): JsonRecord[] {
  return Array.isArray(value) ? value.filter((item): item is JsonRecord => asRecord(item) !== null) : [];
}

function text(record: JsonRecord | null, key: string, fallback = "—"): string {
  return safeText(record?.[key], fallback);
}

function csv(value: string): string[] {
  return [...new Set(value.split(",").map((item) => item.trim()).filter(Boolean))];
}

function errorText(value: unknown): string {
  return value instanceof Error ? value.message : String(value);
}

function JsonPanel({ value }: { value: unknown }) {
  return <pre className="json phase7-json">{pretty(value)}</pre>;
}

function stateClass(state: string): string {
  if (["promoted", "mission_resumed", "canary_passed", "reviewed_pass"].includes(state)) return "good";
  if (["reviewed_rejected", "rolled_back"].includes(state)) return "warn";
  return "pending";
}

export default function Phase7App() {
  const [surface, setSurface] = useState<Surface>("Workspace");
  const [baseUrl, setBaseUrl] = useState(DEFAULT_PHASE7_API_BASE);
  const [token, setToken] = useState("");
  const [health, setHealth] = useState<Phase7Health | null>(null);
  const [connected, setConnected] = useState(false);
  const [evolutions, setEvolutions] = useState<JsonRecord[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [selected, setSelected] = useState<JsonRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [operator, setOperator] = useState("owner");

  const [missionId, setMissionId] = useState("");
  const [parentOperationId, setParentOperationId] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");
  const [attemptId, setAttemptId] = useState("");
  const [resumeToken, setResumeToken] = useState("");
  const [resumeSha, setResumeSha] = useState("");
  const [capabilityId, setCapabilityId] = useState("");
  const [expectedEffects, setExpectedEffects] = useState("");
  const [actualEffects, setActualEffects] = useState("");
  const [manifestSha, setManifestSha] = useState("");
  const [refusalCode, setRefusalCode] = useState("");
  const [evidenceRefs, setEvidenceRefs] = useState("");
  const [summary, setSummary] = useState("");

  const [repositoryId, setRepositoryId] = useState("");
  const [task, setTask] = useState("");
  const [plan, setPlan] = useState("");
  const [files, setFiles] = useState("");
  const [providerId, setProviderId] = useState("");
  const [canarySessionId, setCanarySessionId] = useState("");

  const api = useMemo(() => new Phase7Api({ baseUrl, token }), [baseUrl, token]);
  const state = text(selected, "state", "none");
  const gap = asRecord(selected?.gap);
  const proposal = asRecord(selected?.proposal);
  const approval = asRecord(selected?.approval_binding);
  const engineeringApproval = asRecord(selected?.engineering_approval_binding);
  const childOperation = asRecord(selected?.child_operation);
  const candidate = asRecord(selected?.candidate);
  const review = asRecord(selected?.sergeant_review);
  const canary = asRecord(selected?.canary);
  const promotion = asRecord(selected?.promotion);
  const resume = asRecord(selected?.resume);
  const activeGeneration = asRecord(selected?.active_generation);

  async function reload(preferredId = selectedId): Promise<void> {
    const result = await api.evolutions();
    const items = asRecords(result.evolutions);
    setEvolutions(items);
    const id = preferredId || safeText(items[0]?.evolution_id, "");
    setSelectedId(id);
    setSelected(id ? await api.evolution(id) : null);
  }

  async function connect(): Promise<void> {
    setBusy(true); setError(""); setConnected(false);
    try {
      const publicHealth = await api.health();
      setHealth(publicHealth);
      if (publicHealth.runtime_authority_expansion !== false || publicHealth.model_self_approval !== false) {
        throw new Error("Phase 7 authority invariants are not safe");
      }
      if (!token.trim()) {
        setError("Phase 7 service is reachable. Enter the local bearer token for protected evolution state.");
        return;
      }
      await reload("");
      setConnected(true);
    } catch (cause) {
      setError(errorText(cause));
    } finally { setBusy(false); }
  }

  async function refresh(): Promise<void> {
    if (!connected) return;
    setBusy(true); setError("");
    try {
      setHealth(await api.health());
      await reload();
    } catch (cause) {
      setConnected(false); setSelected(null); setError(errorText(cause));
    } finally { setBusy(false); }
  }

  async function selectEvolution(id: string): Promise<void> {
    setSelectedId(id); setBusy(true); setError("");
    try { setSelected(await api.evolution(id)); } catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  async function action(operation: () => Promise<unknown>): Promise<void> {
    setBusy(true); setError("");
    try { await operation(); await reload(selectedId); }
    catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  async function confirmGap(): Promise<void> {
    setBusy(true); setError("");
    try {
      const record = await api.confirmGap({
        mission_id: missionId,
        parent_operation_id: parentOperationId,
        workspace_id: workspaceId,
        attempt_id: attemptId,
        resume_token: resumeToken,
        resume_state_sha256: resumeSha,
        capability_id: capabilityId,
        expected_effects: csv(expectedEffects),
        actual_effects: csv(actualEffects),
        actual_manifest_sha256: manifestSha,
        refusal_code: refusalCode,
        evidence_refs: csv(evidenceRefs),
        summary,
      });
      const id = safeText(record.evolution_id, "");
      await reload(id);
    } catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  function engineeringIntent(): JsonRecord {
    return {
      repository_id: repositoryId,
      task,
      plan,
      files: csv(files),
      provider_id: providerId,
      apply_plan: true,
      review: "required",
      review_mode: "pull_request",
      mode: "quick_edit",
      client_kind: "workspace",
    };
  }

  function disconnect(): void {
    setConnected(false); setToken(""); setHealth(null); setEvolutions([]); setSelected(null); setSelectedId(""); setError("");
  }

  return <div className="phase7-root">
    <div className="phase7-switcher">
      <div><b>Origins Factory · Phase 7</b><span>Controlled capability evolution. Approval, implementation, review, canary and promotion remain separate authorities.</span></div>
      <div className="phase7-tabs">
        <button className={surface === "Workspace" ? "active" : ""} onClick={() => setSurface("Workspace")}>Workspace</button>
        <button className={surface === "EVOLUTION" ? "active" : ""} onClick={() => setSurface("EVOLUTION")}>EVOLUTION</button>
      </div>
    </div>

    {surface === "Workspace" ? <Phase6App /> : <div className="phase7-console">
      <header className="phase7-header">
        <div><div className="eyebrow">THETECHGUY · ORIGINS FACTORY · CONTROLLED SYNTHESIS</div><h1>EVOLUTION</h1></div>
        <div className={`phase7-status ${connected ? "connected" : health?.ok ? "degraded" : "disconnected"}`}><span />{connected ? "connected" : health?.ok ? "auth required" : "disconnected"}</div>
      </header>

      <section className="phase7-connect">
        <label>Phase 7 endpoint<input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} disabled={connected || busy} /></label>
        <label>local bearer token<input type="password" value={token} onChange={(event) => setToken(event.target.value)} disabled={connected || busy} placeholder="memory only" /></label>
        {!connected ? <button disabled={busy} onClick={() => void connect()}>{busy ? "Connecting…" : "Connect"}</button> : <>
          <button disabled={busy} onClick={() => void refresh()}>Refresh</button>
          <button className="secondary" disabled={busy} onClick={disconnect}>Disconnect</button>
        </>}
      </section>

      {error && <div className="banner error phase7-banner">{error}</div>}
      <div className="phase7-lock"><b>NO SELF-AUTHORITY</b><span>Models cannot confirm their own gap, approve capability or engineering requests, activate a Generation, or widen runtime authority. Promotion never grants a lease by itself.</span></div>

      {!connected ? <main className="phase7-main"><section className="card"><h3>Public authority truth</h3><JsonPanel value={health ?? { runtime_authority_expansion: false, model_self_approval: false }} /></section></main> : <main className="phase7-main phase7-layout">
        <aside className="phase7-sidebar">
          <div className="phase7-sidehead"><b>Evolutions</b><span>{evolutions.length}</span></div>
          {evolutions.map((item) => {
            const id = safeText(item.evolution_id, "");
            const itemGap = asRecord(item.gap);
            return <button key={id} className={selectedId === id ? "selected" : ""} onClick={() => void selectEvolution(id)}>
              <b>{text(itemGap, "capability_id")}</b><span>{safeText(item.state, "unknown")}</span><small>{text(itemGap, "mission_id")}</small>
            </button>;
          })}
          {!evolutions.length && <div className="empty">No capability evolution has been recorded.</div>}
        </aside>

        <section className="phase7-content">
          <article className="card phase7-new">
            <h3>Confirm evidence-backed capability gap</h3>
            <p className="muted">This records evidence and compiles a proposal. It does not approve or activate anything.</p>
            <div className="phase7-form-grid">
              <label>Mission ID<input value={missionId} onChange={(e) => setMissionId(e.target.value)} /></label>
              <label>Parent AgentOps Operation<input value={parentOperationId} onChange={(e) => setParentOperationId(e.target.value)} /></label>
              <label>Workspace ID<input value={workspaceId} onChange={(e) => setWorkspaceId(e.target.value)} /></label>
              <label>Attempt ID<input value={attemptId} onChange={(e) => setAttemptId(e.target.value)} /></label>
              <label>Resume token<input value={resumeToken} onChange={(e) => setResumeToken(e.target.value)} /></label>
              <label>Resume state SHA-256<input value={resumeSha} onChange={(e) => setResumeSha(e.target.value)} /></label>
              <label>Capability ID<input value={capabilityId} onChange={(e) => setCapabilityId(e.target.value)} /></label>
              <label>Actual manifest SHA-256<input value={manifestSha} onChange={(e) => setManifestSha(e.target.value)} /></label>
              <label>Expected effects, comma-separated<input value={expectedEffects} onChange={(e) => setExpectedEffects(e.target.value)} /></label>
              <label>Actual effects, comma-separated<input value={actualEffects} onChange={(e) => setActualEffects(e.target.value)} /></label>
              <label>Bounded refusal code<input value={refusalCode} onChange={(e) => setRefusalCode(e.target.value)} /></label>
              <label>Evidence refs, 2+ comma-separated<input value={evidenceRefs} onChange={(e) => setEvidenceRefs(e.target.value)} /></label>
            </div>
            <label>Gap summary<textarea value={summary} onChange={(e) => setSummary(e.target.value)} /></label>
            <button disabled={busy} onClick={() => void confirmGap()}>Confirm gap + compile proposal</button>
          </article>

          {selected && <>
            <article className="card phase7-overview">
              <div className="phase7-card-head"><div><h3>{text(gap, "capability_id")}</h3><p>{text(gap, "summary")}</p></div><strong className={stateClass(state)}>{state}</strong></div>
              <div className="phase7-truth-grid">
                <div><b>Mission</b><span>{text(gap, "mission_id")}</span></div>
                <div><b>Attempt</b><span>{text(gap, "attempt_id")}</span></div>
                <div><b>Active Generation</b><span>{text(activeGeneration, "generation", "none")}</span></div>
                <div><b>Runtime authority expansion</b><span>FALSE</span></div>
              </div>
            </article>

            <article className="card">
              <h3>Owner-gated progression</h3>
              <label>Decision identity<input value={operator} onChange={(e) => setOperator(e.target.value)} /></label>
              <div className="phase7-actions">
                {state === "proposal_ready" && !approval && <button disabled={busy} onClick={() => void action(() => api.createApproval(selectedId))}>Request capability approval</button>}
                {state === "proposal_ready" && text(approval, "status") === "pending" && <>
                  <button disabled={busy} onClick={() => void action(() => api.decideApproval(selectedId, { approval_id: text(approval, "approval_id"), decision: "approved", decided_by: operator }))}>Approve capability</button>
                  <button className="danger" disabled={busy} onClick={() => void action(() => api.decideApproval(selectedId, { approval_id: text(approval, "approval_id"), decision: "rejected", decided_by: operator }))}>Reject capability</button>
                </>}
                {state === "proposal_ready" && text(approval, "status") === "approved" && <button disabled={busy} onClick={() => void action(() => api.createChildOperation(selectedId, text(approval, "approval_id")))}>Create AgentOps child upgrade Operation</button>}
              </div>

              {state === "upgrade_operation_ready" && <div className="phase7-engineering">
                <h4>CodeOps candidate request</h4>
                <div className="phase7-form-grid">
                  <label>Repository ID<input value={repositoryId} onChange={(e) => setRepositoryId(e.target.value)} /></label>
                  <label>Provider ID (optional)<input value={providerId} onChange={(e) => setProviderId(e.target.value)} /></label>
                  <label>Files, comma-separated<input value={files} onChange={(e) => setFiles(e.target.value)} /></label>
                  <label>Task<input value={task} onChange={(e) => setTask(e.target.value)} /></label>
                </div>
                <label>Reviewed implementation plan path<input value={plan} onChange={(e) => setPlan(e.target.value)} placeholder="relative/path/to/plan.json" /></label>
                <div className="phase7-actions">
                  {!engineeringApproval && <button disabled={busy} onClick={() => void action(() => api.createEngineeringApproval(selectedId, engineeringIntent()))}>Request engineering approval</button>}
                  {text(engineeringApproval, "status") === "pending" && <>
                    <button disabled={busy} onClick={() => void action(() => api.decideEngineeringApproval(selectedId, { approval_id: text(engineeringApproval, "approval_id"), decision: "approved", decided_by: operator }))}>Approve engineering</button>
                    <button className="danger" disabled={busy} onClick={() => void action(() => api.decideEngineeringApproval(selectedId, { approval_id: text(engineeringApproval, "approval_id"), decision: "rejected", decided_by: operator }))}>Reject engineering</button>
                  </>}
                  {text(engineeringApproval, "status") === "approved" && <button disabled={busy} onClick={() => void action(() => api.implementCandidate(selectedId, engineeringIntent()))}>Run CodeOps + Sergeant</button>}
                </div>
              </div>}

              {state === "reviewed_pass" && <div className="phase7-actions phase7-canary">
                <label>Successful Origins canary Session ID<input value={canarySessionId} onChange={(e) => setCanarySessionId(e.target.value)} /></label>
                <button disabled={busy || !canarySessionId.trim()} onClick={() => void action(() => api.recordCanary(selectedId, canarySessionId))}>Bind passed canary</button>
              </div>}

              {state === "canary_passed" && <div className="phase7-actions">
                <button disabled={busy} onClick={() => void action(() => api.decide(selectedId, "promote", operator))}>Promote Generation</button>
                <button className="danger" disabled={busy} onClick={() => void action(() => api.decide(selectedId, "rollback", operator))}>Rollback candidate</button>
              </div>}

              {(state === "promoted" || state === "rolled_back") && <button disabled={busy} onClick={() => void action(() => api.resume(selectedId))}>Resume original Mission</button>}
              {state === "reviewed_rejected" && <div className="banner warn embedded">Sergeant rejected the candidate. No canary or promotion is permitted.</div>}
            </article>

            <div className="phase7-stage-grid">
              <article className="card"><h3>Gap + Proposal</h3><JsonPanel value={{ gap, proposal }} /></article>
              <article className="card"><h3>AgentOps approvals</h3><JsonPanel value={{ capability: approval, engineering: engineeringApproval }} /></article>
              <article className="card"><h3>Child Operation</h3><JsonPanel value={childOperation} /></article>
              <article className="card"><h3>Generation Candidate</h3><JsonPanel value={candidate} /></article>
              <article className="card"><h3>Sergeant Review</h3><JsonPanel value={review} /></article>
              <article className="card"><h3>Canary</h3><JsonPanel value={canary} /></article>
              <article className="card"><h3>Promotion / Rollback</h3><JsonPanel value={promotion} /></article>
              <article className="card"><h3>Mission Resume</h3><JsonPanel value={resume} /></article>
            </div>
          </>}
        </section>
      </main>}
    </div>}
  </div>;
}
