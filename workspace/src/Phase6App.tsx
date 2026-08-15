import { useMemo, useState } from "react";
import Phase5App from "./Phase5App";
import { pretty, safeText, type JsonRecord } from "./model";
import { DEFAULT_PHASE6_API_BASE, Phase6Api, type Phase6Health } from "./phase6Api";
import "./phase6.css";

type Phase6Surface = "Workspace" | "XRAY";

function asRecord(value: unknown): JsonRecord | null {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as JsonRecord : null;
}

function asRecords(value: unknown): JsonRecord[] {
  return Array.isArray(value) ? value.filter((item): item is JsonRecord => asRecord(item) !== null) : [];
}

function text(record: JsonRecord | null, key: string, fallback = "—"): string {
  return safeText(record?.[key], fallback);
}

function bool(record: JsonRecord | null, key: string): boolean {
  return record?.[key] === true;
}

function JsonPanel({ value }: { value: unknown }) {
  return <pre className="json phase6-json">{pretty(value)}</pre>;
}

function Truth({ label, value, warning = false }: { label: string; value: string; warning?: boolean }) {
  return <div className={`truth ${warning ? "warn" : ""}`}><b>{label}</b><span>{value}</span></div>;
}

function Empty({ children }: { children: string }) {
  return <div className="empty">{children}</div>;
}

function latestContract(gateway: JsonRecord | null, contractType: string): JsonRecord | null {
  const contracts = asRecord(gateway?.contracts);
  const entries = asRecords(contracts?.[contractType]);
  if (!entries.length) return null;
  return asRecord(entries[entries.length - 1]?.contract);
}

function contractPayload(gateway: JsonRecord | null, contractType: string): JsonRecord | null {
  return asRecord(latestContract(gateway, contractType)?.payload);
}

function errorText(value: unknown): string {
  return value instanceof Error ? value.message : String(value);
}

export default function Phase6App() {
  const [surface, setSurface] = useState<Phase6Surface>("Workspace");
  const [baseUrl, setBaseUrl] = useState(DEFAULT_PHASE6_API_BASE);
  const [token, setToken] = useState("");
  const [health, setHealth] = useState<Phase6Health | null>(null);
  const [projection, setProjection] = useState<JsonRecord | null>(null);
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const api = useMemo(() => new Phase6Api({ baseUrl, token }), [baseUrl, token]);
  const gateway = asRecord(projection?.gateway);
  const xray = asRecord(projection?.xray);
  const gatewayOwner = asRecord(gateway?.gateway);
  const gatewayHealth = asRecord(gatewayOwner?.health);
  const doctor = asRecord(gatewayOwner?.doctor);
  const snapshot = asRecord(gatewayOwner?.snapshot);
  const journal = asRecord(gatewayOwner?.journal);
  const writeExecution = asRecord(projection?.write_execution);
  const agentopsLink = asRecord(projection?.agentops_operation_link);
  const sessions = asRecords(snapshot?.physical_sessions);
  const operations = asRecords(snapshot?.operation_sessions);
  const endpoints = asRecords(gateway?.endpoint_observations);
  const twin = contractPayload(gateway, "device_twin");
  const evidence = contractPayload(gateway, "device_evidence");
  const decision = contractPayload(gateway, "decision_verdict");
  const modeLease = contractPayload(gateway, "mode_lease");
  const executionLease = contractPayload(gateway, "execution_lease");
  const verification = contractPayload(gateway, "verification_result");
  const recovery = contractPayload(gateway, "recovery_plan");
  const xrayManifest = asRecord(xray?.manifest);
  const xraySignature = asRecord(xray?.signature);
  const xrayEvidence = asRecord(xray?.evidence);

  async function connect(): Promise<void> {
    setBusy(true); setError(""); setConnected(false); setProjection(null);
    try {
      const publicHealth = await api.health();
      setHealth(publicHealth);
      if (!token.trim()) {
        setError("Phase 6 service is reachable. Enter the local bearer token to load protected device projections.");
        return;
      }
      const protectedProjection = await api.device();
      setProjection(protectedProjection);
      setConnected(true);
    } catch (cause) {
      setError(errorText(cause));
      setConnected(false);
    } finally { setBusy(false); }
  }

  async function refresh(): Promise<void> {
    if (!connected) return;
    setBusy(true); setError("");
    try {
      setHealth(await api.health());
      setProjection(await api.device());
    } catch (cause) {
      setError(errorText(cause));
      setProjection(null);
      setConnected(false);
    } finally { setBusy(false); }
  }

  function disconnect(): void {
    setConnected(false);
    setProjection(null);
    setHealth(null);
    setToken("");
    setError("");
  }

  return <div className="phase6-root">
    <div className="phase6-switcher">
      <div>
        <b>Origins Factory · Phase 6</b>
        <span>Device read-only integration. Huawei Gateway and TTG Device X-Ray retain specialist truth.</span>
      </div>
      <div className="phase6-tabs">
        <button className={surface === "Workspace" ? "active" : ""} onClick={() => setSurface("Workspace")}>Workspace</button>
        <button className={surface === "XRAY" ? "active" : ""} onClick={() => setSurface("XRAY")}>XRAY</button>
      </div>
    </div>

    {surface === "Workspace" ? <Phase5App /> : <div className="phase6-console">
      <header className="phase6-header">
        <div><div className="eyebrow">THETECHGUY · ORIGINS FACTORY · DEVICE READ-ONLY</div><h1>XRAY</h1></div>
        <div className={`phase6-status ${connected ? "connected" : health?.ok ? "degraded" : "disconnected"}`}>
          <span />{connected ? "connected" : health?.ok ? "auth required" : "disconnected"}
        </div>
      </header>

      <section className="phase6-connect">
        <label>Phase 6 owner endpoint<input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} disabled={connected || busy} /></label>
        <label>local bearer token<input type="password" value={token} onChange={(event) => setToken(event.target.value)} disabled={connected || busy} placeholder="memory only" /></label>
        {!connected ? <button disabled={busy} onClick={() => void connect()}>{busy ? "Connecting…" : "Connect"}</button> : <>
          <button disabled={busy} onClick={() => void refresh()}>Refresh evidence</button>
          <button className="secondary" disabled={busy} onClick={disconnect}>Disconnect</button>
        </>}
      </section>

      {error && <div className="banner error phase6-banner">{error}</div>}

      <main className="phase6-main">
        {!connected ? <section>
          <div className="phase6-lock-banner"><b>NO DEVICE WRITE API</b><span>Phase 6 can inspect owner state only. No flash, erase, reboot, loader, partition write, lease consumption or Gateway state transition is mounted.</span></div>
          <Empty>Connect with the local Origins bearer to inspect protected Huawei Gateway and X-Ray owner projections.</Empty>
          {health && <article className="card phase6-health"><h3>Public Phase 6 health</h3><JsonPanel value={health} /></article>}
        </section> : <section>
          <div className="phase6-lock-banner"><b>READ-ONLY AUTHORITY LOCK</b><span>Mechanical write execution remains unavailable even if the Gateway journal contains historical execution leases or results.</span></div>

          <div className="phase6-metrics">
            <article><strong>{text(gatewayHealth, "status", "OFF").toUpperCase()}</strong><span>Huawei Gateway</span></article>
            <article><strong>{sessions.length}</strong><span>Physical Sessions</span></article>
            <article><strong>{operations.length}</strong><span>Gateway Operations</span></article>
            <article><strong>{xray?.available === true ? "VERIFIED" : "UNAVAILABLE"}</strong><span>X-Ray Bundle</span></article>
          </div>

          <div className="grid two">
            <article className="card">
              <h3>Authority boundary</h3>
              <Truth label="Gateway device authority" value={text(gatewayHealth, "device_authority")} warning={text(gatewayHealth, "device_authority") !== "none"} />
              <Truth label="X-Ray authority" value={text(gatewayHealth, "xray_authority")} warning={text(gatewayHealth, "xray_authority") !== "read_only"} />
              <Truth label="Journal chain" value={bool(journal, "journal_valid") ? "VERIFIED" : "INVALID"} warning={!bool(journal, "journal_valid")} />
              <Truth label="Write execution" value={writeExecution?.available === false ? text(writeExecution, "reason") : "UNEXPECTEDLY AVAILABLE"} warning />
              <Truth label="AgentOps ↔ Gateway durable link" value={agentopsLink?.available === true ? "AVAILABLE" : text(agentopsLink, "reason")} warning={agentopsLink?.available !== true} />
            </article>
            <article className="card">
              <h3>Owner revisions recovered</h3>
              <Truth label="Huawei Gateway owner" value={text(gateway, "owner_revision_recovered")} />
              <Truth label="TTG Device X-Ray owner" value={text(xray, "owner_revision_recovered", xray?.available === false ? "not configured" : "—")} warning={xray?.available !== true} />
              <Truth label="Gateway health" value={bool(doctor, "healthy") ? "HEALTHY" : "DEGRADED"} warning={!bool(doctor, "healthy")} />
              <Truth label="Recovering operations" value={text(doctor, "recovering_operation_sessions", "0")} warning={Number(doctor?.recovering_operation_sessions ?? 0) > 0} />
            </article>
          </div>

          <div className="grid two">
            <article className="card"><h3>Physical Device Sessions</h3>
              {sessions.length ? <div className="phase6-list">{sessions.map((session, index) => <div className="phase6-row" key={text(session, "session_id", String(index))}><div><b>{text(session, "session_id")}</b><span>{text(session, "state")} · recovery {text(session, "recovery_count", "0")}</span></div><code>{text(session, "fingerprint_sha256")}</code></div>)}</div> : <Empty>No Gateway physical session is present.</Empty>}
            </article>
            <article className="card"><h3>Gateway Operations</h3>
              {operations.length ? <div className="phase6-list">{operations.map((operation, index) => <div className="phase6-row" key={text(operation, "operation_id", String(index))}><div><b>{text(operation, "operation_id")}</b><span>{text(operation, "stage")} · {text(operation, "status")} · recovery {text(operation, "recovery_count", "0")}</span></div><code>{text(operation, "request_sha256")}</code></div>)}</div> : <Empty>No Gateway Operation is present.</Empty>}
            </article>
          </div>

          <article className="card"><h3>Endpoint observations</h3>
            {endpoints.length ? <div className="phase6-endpoints">{endpoints.map((endpoint, index) => <div className="phase6-endpoint" key={text(endpoint, "observation_id", String(index))}><b>{text(endpoint, "transport")} · {text(endpoint, "mode")}</b><span>{text(endpoint, "endpoint_key")} · {text(endpoint, "observed_at")}</span></div>)}</div> : <Empty>No endpoint observation is present in the recovered journal window.</Empty>}
          </article>

          <div className="phase6-contract-grid">
            <article className="card"><h3>Pre/Post Device Twin</h3>{twin ? <JsonPanel value={twin} /> : <Empty>No Device Twin contract is present.</Empty>}</article>
            <article className="card"><h3>Device Evidence</h3>{evidence ? <JsonPanel value={evidence} /> : <Empty>No Device Evidence contract is present.</Empty>}</article>
            <article className="card"><h3>Decision Verdict</h3>{decision ? <JsonPanel value={decision} /> : <Empty>No Decision Verdict contract is present.</Empty>}</article>
            <article className="card"><h3>Mode Lease</h3>{modeLease ? <JsonPanel value={modeLease} /> : <Empty>No Mode Lease contract is present.</Empty>}</article>
            <article className="card"><h3>Historical Execution Lease</h3>{executionLease ? <><div className="banner warn embedded">Display only. Phase 6 cannot consume or execute this lease.</div><JsonPanel value={executionLease} /></> : <Empty>No Execution Lease contract is present.</Empty>}</article>
            <article className="card"><h3>Verification Result</h3>{verification ? <JsonPanel value={verification} /> : <Empty>No Verification Result contract is present.</Empty>}</article>
            <article className="card phase6-wide"><h3>Recovery Plan</h3>{recovery ? <JsonPanel value={recovery} /> : <Empty>No Recovery Plan contract is present.</Empty>}</article>
          </div>

          <article className="card phase6-xray-card">
            <div className="phase6-card-head"><div><h3>TTG Device X-Ray sealed bundle</h3><p className="muted">Digest verification is mandatory. HMAC is reported separately and is never inferred from a SIGNED label alone.</p></div><strong>{xray?.available === true ? (bool(xray, "expired") ? "EXPIRED" : "CURRENT") : "NOT MOUNTED"}</strong></div>
            {xray?.available === true ? <>
              <div className="grid two">
                <div>
                  <Truth label="Bundle integrity" value={bool(xray, "integrity_verified") ? "SHA-256 VERIFIED" : "INVALID"} warning={!bool(xray, "integrity_verified")} />
                  <Truth label="Bundle write_allowed" value={xray?.write_allowed === false ? "false" : "INVALID"} warning={xray?.write_allowed !== false} />
                  <Truth label="Signature status" value={text(xraySignature, "status")} warning={!bool(xraySignature, "cryptographically_verified")} />
                  <Truth label="HMAC verification" value={bool(xraySignature, "cryptographically_verified") ? "VERIFIED" : text(xraySignature, "verification_reason")} warning={!bool(xraySignature, "cryptographically_verified")} />
                </div>
                <JsonPanel value={xrayManifest} />
              </div>
              <div className="phase6-contract-grid">
                <article className="phase6-subcard"><h3>Certification</h3>{asRecord(xrayEvidence?.certification) ? <JsonPanel value={xrayEvidence?.certification} /> : <Empty>Not present.</Empty>}</article>
                <article className="phase6-subcard"><h3>Profile Match</h3>{asRecord(xrayEvidence?.profile_match) ? <JsonPanel value={xrayEvidence?.profile_match} /> : <Empty>Not present.</Empty>}</article>
                <article className="phase6-subcard"><h3>Recommended Plan</h3>{asRecord(xrayEvidence?.recommended_plan) ? <JsonPanel value={xrayEvidence?.recommended_plan} /> : <Empty>Not present.</Empty>}</article>
                <article className="phase6-subcard"><h3>Device Identity</h3>{asRecord(xrayEvidence?.device_identity) ? <JsonPanel value={xrayEvidence?.device_identity} /> : <Empty>Not present.</Empty>}</article>
              </div>
            </> : <div className="banner warn embedded">{text(xray, "reason", "XRAY_BUNDLE_NOT_CONFIGURED")}</div>}
          </article>
        </section>}
      </main>
    </div>}
  </div>;
}
