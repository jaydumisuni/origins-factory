import { FormEvent, useMemo, useState } from "react";
import Phase4App from "./Phase4App";
import { DEFAULT_API_BASE } from "./api";
import { pretty, safeText, type JsonRecord } from "./model";
import { DEFAULT_PHASE5_API_BASE, Phase5Api, type Phase5Health } from "./phase5Api";
import "./phase5.css";

type Surface = "Core" | "Oracle" | "Logistics" | "Applications";
const surfaces: Surface[] = ["Core", "Oracle", "Logistics", "Applications"];

function asRecord(value: unknown): JsonRecord | null {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as JsonRecord : null;
}

function records(value: unknown): JsonRecord[] {
  return Array.isArray(value) ? value.filter((item): item is JsonRecord => asRecord(item) !== null) : [];
}

function text(record: JsonRecord | null, key: string, fallback = ""): string {
  const value = record?.[key];
  return typeof value === "string" ? value : fallback;
}

function bool(record: JsonRecord | null, key: string): boolean {
  return record?.[key] === true;
}

function JsonPanel({ value }: { value: unknown }) {
  return <pre className="json">{pretty(value)}</pre>;
}

function Empty({ children }: { children: string }) {
  return <div className="empty">{children}</div>;
}

function Truth({ label, value, warning = false }: { label: string; value: string; warning?: boolean }) {
  return <div className={`truth ${warning ? "warn" : ""}`}><b>{label}</b><span>{value}</span></div>;
}

function errorText(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason);
}

function artifactCandidate(value: JsonRecord | null): JsonRecord | null {
  return value ? asRecord(value.artifact_candidate) : null;
}

export default function Phase5App() {
  const [surface, setSurface] = useState<Surface>("Core");
  const [originsBaseUrl, setOriginsBaseUrl] = useState(DEFAULT_API_BASE);
  const [phase5BaseUrl, setPhase5BaseUrl] = useState(DEFAULT_PHASE5_API_BASE);
  const [token, setToken] = useState("");
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [health, setHealth] = useState<Phase5Health | null>(null);
  const [browser, setBrowser] = useState<JsonRecord | null>(null);
  const [remoteNode, setRemoteNode] = useState<JsonRecord | null>(null);
  const [lumi, setLumi] = useState<JsonRecord | null>(null);
  const [applications, setApplications] = useState<JsonRecord[]>([]);
  const [artifacts, setArtifacts] = useState<JsonRecord[]>([]);

  const [actApproved, setActApproved] = useState(false);
  const [remotePath, setRemotePath] = useState("");
  const [remoteApproved, setRemoteApproved] = useState(false);
  const [remoteReceipt, setRemoteReceipt] = useState<JsonRecord | null>(null);
  const [oracleArtifactWorkspace, setOracleArtifactWorkspace] = useState("");
  const [oracleArtifactResult, setOracleArtifactResult] = useState<JsonRecord | null>(null);

  const [downloadUrl, setDownloadUrl] = useState("");
  const [downloadFilename, setDownloadFilename] = useState("");
  const [downloadQueue, setDownloadQueue] = useState("default");
  const [downloadPriority, setDownloadPriority] = useState(0);
  const [downloadPaused, setDownloadPaused] = useState(false);
  const [lumiTask, setLumiTask] = useState<JsonRecord | null>(null);
  const [lumiCandidate, setLumiCandidate] = useState<JsonRecord | null>(null);
  const [lumiArtifactWorkspace, setLumiArtifactWorkspace] = useState("");
  const [lumiArtifactResult, setLumiArtifactResult] = useState<JsonRecord | null>(null);
  const [artifactWorkspaceFilter, setArtifactWorkspaceFilter] = useState("");

  const [applicationWorkspace, setApplicationWorkspace] = useState("");
  const [launchResult, setLaunchResult] = useState<JsonRecord | null>(null);

  const api = useMemo(
    () => new Phase5Api({ originsBaseUrl, phase5BaseUrl, token }),
    [originsBaseUrl, phase5BaseUrl, token],
  );

  const remoteApplication = asRecord(remoteNode?.remote_application_attachment);
  const remoteCandidate = artifactCandidate(remoteReceipt);
  const nodeAvailable = bool(remoteNode, "available");
  const browserAvailable = bool(browser, "available");
  const lumiAvailable = bool(lumi, "available");

  async function loadOwners(): Promise<void> {
    const results = await Promise.allSettled([
      api.browser(),
      api.remoteNode(),
      api.lumi(),
      api.applications(),
      api.artifacts(artifactWorkspaceFilter.trim()),
    ]);
    const [browserResult, nodeResult, lumiResult, appResult, artifactResult] = results;
    setBrowser(browserResult.status === "fulfilled" ? browserResult.value : { available: false, error: errorText(browserResult.reason) });
    setRemoteNode(nodeResult.status === "fulfilled" ? nodeResult.value : { available: false, error: errorText(nodeResult.reason) });
    setLumi(lumiResult.status === "fulfilled" ? lumiResult.value : { available: false, error: errorText(lumiResult.reason) });
    setApplications(appResult.status === "fulfilled" ? appResult.value.applications ?? [] : []);
    setArtifacts(artifactResult.status === "fulfilled" ? artifactResult.value.artifacts ?? [] : []);
    const failures = results.filter((item) => item.status === "rejected") as PromiseRejectedResult[];
    if (failures.length) setError(failures.map((item) => errorText(item.reason)).join(" · "));
  }

  async function connect(): Promise<void> {
    setBusy(true); setError("");
    try {
      setHealth(await api.health());
      if (!token.trim()) {
        setConnected(false);
        setError("Phase 5 service is reachable. Enter the local bearer token to load owner projections.");
        return;
      }
      await loadOwners();
      setConnected(true);
    } catch (cause) {
      setConnected(false);
      setError(errorText(cause));
    } finally { setBusy(false); }
  }

  async function refresh(): Promise<void> {
    if (!connected) return;
    setBusy(true); setError("");
    try {
      setHealth(await api.health());
      await loadOwners();
    } catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  function disconnect(): void {
    setConnected(false); setToken(""); setHealth(null); setError("");
    setBrowser(null); setRemoteNode(null); setLumi(null); setApplications([]); setArtifacts([]);
    setRemoteReceipt(null); setLumiTask(null); setLumiCandidate(null); setLaunchResult(null);
  }

  async function handoff(authority: "observe" | "assist" | "act"): Promise<void> {
    setBusy(true); setError("");
    try {
      if (authority === "act" && !actApproved) throw new Error("Explicit owner approval is required before Oracle Act handoff.");
      await api.setBrowserAuthority(authority, authority === "act" && actApproved);
      setBrowser(await api.browser());
      if (authority === "act") setActApproved(false);
    } catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  async function humanTakeover(): Promise<void> {
    setBusy(true); setError("");
    try { await api.humanTakeover(); setBrowser(await api.browser()); }
    catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  async function retrieveRemote(event: FormEvent): Promise<void> {
    event.preventDefault(); setBusy(true); setError(""); setRemoteReceipt(null); setOracleArtifactResult(null);
    try {
      if (!remoteApproved) throw new Error("Approve this exact read-only remote file retrieval before continuing.");
      const receipt = await api.retrieveRemoteFile(remotePath.trim(), true);
      setRemoteReceipt(receipt);
      setRemoteApproved(false);
      setRemoteNode(await api.remoteNode());
    } catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  async function promoteOracleCandidate(): Promise<void> {
    if (!remoteReceipt || !remoteCandidate) return;
    setBusy(true); setError("");
    try {
      const path = text(remoteCandidate, "path", text(remoteReceipt, "local_path"));
      const ownerRef = text(remoteReceipt, "stream_id", text(remoteReceipt, "sha256"));
      if (!path || !ownerRef) throw new Error("Oracle receipt does not contain a promotable Artifact source reference.");
      const result = await api.registerArtifact({
        workspace_id: oracleArtifactWorkspace.trim(),
        owner: "oracle",
        owner_ref: ownerRef,
        path,
        filename: text(remoteCandidate, "filename"),
        media_type: "application/octet-stream",
      });
      setOracleArtifactResult(result);
      setArtifacts((await api.artifacts(artifactWorkspaceFilter.trim())).artifacts ?? []);
    } catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  async function queueDownload(event: FormEvent): Promise<void> {
    event.preventDefault(); setBusy(true); setError(""); setLumiCandidate(null); setLumiArtifactResult(null);
    try {
      const task = await api.queueLumiDownload({
        url: downloadUrl.trim(),
        filename: downloadFilename.trim(),
        queue_id: downloadQueue.trim() || "default",
        priority: downloadPriority,
        start_paused: downloadPaused,
      });
      setLumiTask(task);
      setLumi(await api.lumi());
    } catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  async function refreshLumiTask(): Promise<void> {
    const taskId = text(lumiTask, "id");
    if (!taskId) return;
    setBusy(true); setError("");
    try { setLumiTask(await api.lumiTask(taskId)); }
    catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  async function recoverLumiCandidate(): Promise<void> {
    const taskId = text(lumiTask, "id");
    if (!taskId) return;
    setBusy(true); setError("");
    try { setLumiCandidate(await api.lumiArtifactCandidate(taskId)); }
    catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  async function promoteLumiCandidate(): Promise<void> {
    if (!lumiCandidate) return;
    setBusy(true); setError("");
    try {
      const path = text(lumiCandidate, "path");
      const taskId = text(lumiCandidate, "owner_task_id", text(lumiTask, "id"));
      if (!path || !taskId) throw new Error("Lumi candidate does not contain its owner path/task reference.");
      const result = await api.registerArtifact({
        workspace_id: lumiArtifactWorkspace.trim(),
        owner: "lumi",
        owner_ref: taskId,
        path,
        filename: text(lumiCandidate, "filename"),
        media_type: text(lumiCandidate, "content_type"),
      });
      setLumiArtifactResult(result);
      setArtifacts((await api.artifacts(artifactWorkspaceFilter.trim())).artifacts ?? []);
    } catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  async function refreshArtifacts(event?: FormEvent): Promise<void> {
    event?.preventDefault(); setBusy(true); setError("");
    try { setArtifacts((await api.artifacts(artifactWorkspaceFilter.trim())).artifacts ?? []); }
    catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  async function downloadArtifact(artifact: JsonRecord): Promise<void> {
    const artifactId = text(artifact, "artifact_id");
    if (!artifactId) return;
    setBusy(true); setError("");
    try {
      const blob = await api.artifactContent(artifactId);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = text(artifact, "filename", `${artifactId}.bin`);
      document.body.appendChild(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url);
    } catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  async function launchApplication(application: JsonRecord): Promise<void> {
    const applicationId = text(application, "application_id");
    if (!applicationId || !applicationWorkspace.trim()) return;
    const launchId = crypto.randomUUID();
    setBusy(true); setError("");
    try { setLaunchResult(await api.launchApplication(applicationId, applicationWorkspace.trim(), launchId)); }
    catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  if (surface === "Core") {
    return <div className="phase5-root">
      <div className="phase5-switcher">
        <div><b>Origins Factory · Phase 5</b><span>Mission core remains the proven Phase-4 workspace; owner surfaces are mounted beside it.</span></div>
        <div className="phase5-tabs">{surfaces.map((item) => <button key={item} className={surface === item ? "active" : ""} onClick={() => setSurface(item)}>{item}</button>)}</div>
      </div>
      <Phase4App />
    </div>;
  }

  return <div className="phase5-root phase5-console">
    <header className="phase5-header">
      <div><div className="eyebrow">THETECHGUY · ORIGINS FACTORY · PHASE 5</div><h1>{surface}</h1></div>
      <div className={`phase5-status ${connected ? "connected" : health?.ok ? "degraded" : "disconnected"}`}><span />{connected ? "connected" : health?.ok ? "auth required" : "disconnected"}</div>
    </header>
    <div className="phase5-switcher embedded">
      <div><b>Owner-mounted surfaces</b><span>Oracle and Lumi remain canonical owners; originsd retains durable mechanical truth.</span></div>
      <div className="phase5-tabs">{surfaces.map((item) => <button key={item} className={surface === item ? "active" : ""} onClick={() => setSurface(item)}>{item}</button>)}</div>
    </div>
    <section className="phase5-connect">
      <label>originsd endpoint<input value={originsBaseUrl} onChange={(event) => setOriginsBaseUrl(event.target.value)} disabled={connected || busy} /></label>
      <label>Phase 5 owner endpoint<input value={phase5BaseUrl} onChange={(event) => setPhase5BaseUrl(event.target.value)} disabled={connected || busy} /></label>
      <label>local bearer token<input type="password" value={token} onChange={(event) => setToken(event.target.value)} disabled={connected || busy} placeholder="memory only" /></label>
      {!connected ? <button disabled={busy} onClick={() => void connect()}>{busy ? "Connecting…" : "Connect"}</button> : <><button disabled={busy} onClick={() => void refresh()}>Refresh</button><button className="secondary" onClick={disconnect}>Disconnect</button></>}
    </section>
    {error && <div className="banner error phase5-banner">{error}</div>}

    <main className="phase5-main">
      {!connected ? <section><Empty>Connect with the local Origins bearer to load protected Phase-5 owner projections.</Empty>{health && <article className="card phase5-health"><h3>Public owner health</h3><JsonPanel value={health} /></article>}</section> : <>
        {surface === "Oracle" && <section>
          <h2>Oracle</h2><p className="lead">Retained browser authority and approved remote file access. Oracle remains the owner of browser/remote transport.</p>
          <div className="phase5-metrics">
            <article><strong>{browserAvailable ? "READY" : "OFF"}</strong><span>Browser</span></article>
            <article><strong>{nodeAvailable ? "ONLINE" : "OFF"}</strong><span>Remote Node</span></article>
            <article><strong>{safeText(remoteNode?.node_id)}</strong><span>Exact Node identity</span></article>
            <article><strong>{bool(remoteApplication, "available") ? "READY" : "UNAVAILABLE"}</strong><span>Remote application attachment</span></article>
          </div>
          <div className="grid two">
            <article className="card"><h3>Retained browser Session</h3>{browser ? <JsonPanel value={browser} /> : <Empty>No Oracle browser projection.</Empty>}
              <div className="phase5-actions"><button disabled={busy} onClick={() => void handoff("observe")}>Observe</button><button disabled={busy} onClick={() => void handoff("assist")}>Assist</button><button disabled={busy || !actApproved} onClick={() => void handoff("act")}>Give AI Act</button><button className="takeover" disabled={busy} onClick={() => void humanTakeover()}>Human takeover</button></div>
              <label className="approval-check"><input type="checkbox" checked={actApproved} onChange={(event) => setActApproved(event.target.checked)} /> I explicitly approve Act authority for this handoff.</label>
            </article>
            <article className="card"><h3>Remote Node truth</h3>{remoteNode ? <JsonPanel value={remoteNode} /> : <Empty>No remote Node projection.</Empty>}
              <Truth label="Node routing" value={nodeAvailable ? "Exact configured Node verified" : text(remoteNode, "reason", "Unavailable")} warning={!nodeAvailable} />
              <Truth label="Remote native application Session" value={bool(remoteApplication, "available") ? "Available" : text(remoteApplication, "reason", "Owner contract unavailable")} warning={!bool(remoteApplication, "available")} />
            </article>
          </div>
          <article className="card"><h3>Approved remote file retrieval</h3><p className="muted">Read-only. The browser cannot select the Node, token, local destination, upload mode or overwrite behavior.</p>
            <form onSubmit={retrieveRemote}><input value={remotePath} onChange={(event) => setRemotePath(event.target.value)} placeholder="absolute remote path on the configured Oracle Node" required />
              <label className="approval-check"><input type="checkbox" checked={remoteApproved} onChange={(event) => setRemoteApproved(event.target.checked)} /> Approve this exact read-only retrieval.</label><button disabled={busy || !remoteApproved}>Retrieve + verify</button></form>
            {remoteReceipt && <div className="phase5-result"><JsonPanel value={remoteReceipt} />
              {remoteCandidate && <div className="candidate-box"><h3>Promote verified transfer to Artifact</h3><input value={oracleArtifactWorkspace} onChange={(event) => setOracleArtifactWorkspace(event.target.value)} placeholder="workspace id" /><button disabled={busy || !oracleArtifactWorkspace.trim()} onClick={() => void promoteOracleCandidate()}>Promote candidate</button>{oracleArtifactResult && <JsonPanel value={oracleArtifactResult} />}</div>}
            </div>}
          </article>
        </section>}

        {surface === "Logistics" && <section>
          <h2>Logistics</h2><p className="lead">Lumi owns acquisition, queues, resume and verification. Origins promotes only completed owner output into durable Artifacts.</p>
          <div className="phase5-metrics"><article><strong>{lumiAvailable ? "READY" : "OFF"}</strong><span>Lumi</span></article><article><strong>{artifacts.length}</strong><span>Loaded Artifacts</span></article><article><strong>{text(lumiTask, "status", "—")}</strong><span>Active task</span></article><article><strong>{lumiCandidate ? "READY" : "—"}</strong><span>Artifact candidate</span></article></div>
          <div className="grid two">
            <article className="card"><h3>Lumi owner state</h3>{lumi ? <JsonPanel value={lumi} /> : <Empty>No Lumi projection.</Empty>}</article>
            <article className="card"><h3>Queue acquisition</h3><form onSubmit={queueDownload}><input value={downloadUrl} onChange={(event) => setDownloadUrl(event.target.value)} placeholder="https:// source URL" required /><input value={downloadFilename} onChange={(event) => setDownloadFilename(event.target.value)} placeholder="optional filename" /><div className="phase5-form-row"><input value={downloadQueue} onChange={(event) => setDownloadQueue(event.target.value)} placeholder="queue id" /><input type="number" value={downloadPriority} onChange={(event) => setDownloadPriority(Number(event.target.value))} /></div><label className="approval-check"><input type="checkbox" checked={downloadPaused} onChange={(event) => setDownloadPaused(event.target.checked)} /> Start paused</label><button disabled={busy}>Queue with Lumi</button></form></article>
          </div>
          {lumiTask && <article className="card"><h3>Lumi task</h3><JsonPanel value={lumiTask} /><div className="phase5-actions"><button disabled={busy} onClick={() => void refreshLumiTask()}>Refresh owner task</button><button disabled={busy} onClick={() => void recoverLumiCandidate()}>Recover completed Artifact candidate</button></div>{lumiCandidate && <div className="candidate-box"><JsonPanel value={lumiCandidate} /><input value={lumiArtifactWorkspace} onChange={(event) => setLumiArtifactWorkspace(event.target.value)} placeholder="workspace id" /><button disabled={busy || !lumiArtifactWorkspace.trim()} onClick={() => void promoteLumiCandidate()}>Promote Lumi candidate</button>{lumiArtifactResult && <JsonPanel value={lumiArtifactResult} />}</div>}</article>}
          <article className="card"><div className="phase5-card-head"><div><h3>Durable Artifacts</h3><p className="muted">Origins-owned immutable content store with owner provenance.</p></div><form className="phase5-filter" onSubmit={refreshArtifacts}><input value={artifactWorkspaceFilter} onChange={(event) => setArtifactWorkspaceFilter(event.target.value)} placeholder="optional workspace id" /><button disabled={busy}>Filter</button></form></div>
            {artifacts.length ? <div className="artifact-list">{artifacts.map((artifact, index) => <div className="artifact-row" key={text(artifact, "artifact_id", String(index))}><div><b>{text(artifact, "filename", text(artifact, "artifact_id", "Artifact"))}</b><span>{text(artifact, "owner", "unknown owner")} · {safeText(artifact.size_bytes)} bytes · {text(artifact, "content_sha256", text(artifact, "sha256"))}</span></div><button disabled={busy} onClick={() => void downloadArtifact(artifact)}>Download registered bytes</button></div>)}</div> : <Empty>No Artifacts match this projection.</Empty>}
          </article>
        </section>}

        {surface === "Applications" && <section>
          <h2>Workspace Applications</h2><p className="lead">Local applications launch only from the server-owned registry. Remote application attachment remains separate Oracle authority.</p>
          <div className="grid two"><article className="card"><h3>Launch boundary</h3><input value={applicationWorkspace} onChange={(event) => setApplicationWorkspace(event.target.value)} placeholder="workspace id required for launch" /><Truth label="Executable / argv / cwd" value="Server registry owns all three" /><Truth label="Browser-supplied launch args" value="Not accepted" /><Truth label="Durable launch identity" value="UUID bound to Workspace + application" /></article><article className="card"><h3>Remote application attachment</h3><Truth label="Oracle desktop application Session" value={bool(remoteApplication, "available") ? "Available" : text(remoteApplication, "reason", "ORACLE_DESKTOP_APPLICATION_SESSION_CONTRACT_UNAVAILABLE")} warning={!bool(remoteApplication, "available")} />{remoteApplication && <JsonPanel value={remoteApplication} />}</article></div>
          <article className="card"><h3>Registered local applications</h3>{applications.length ? <div className="application-grid">{applications.map((application, index) => <div className="application-tile" key={text(application, "application_id", String(index))}><div><b>{text(application, "name", text(application, "application_id", "Application"))}</b><span>{text(application, "application_id")} · {text(application, "executable_name")}</span></div><button disabled={busy || !applicationWorkspace.trim() || application.launchable !== true} onClick={() => void launchApplication(application)}>Launch</button></div>)}</div> : <Empty>No applications are registered on this Origins host.</Empty>}</article>
          {launchResult && <article className="card"><h3>Durable launch receipt</h3><JsonPanel value={launchResult} /></article>}
        </section>}
      </>}
    </main>
  </div>;
}
