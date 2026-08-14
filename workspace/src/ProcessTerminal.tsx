import { FormEvent, useState } from "react";
import type { OriginsApi } from "./api";
import type { JsonRecord, RepositorySnapshot } from "./model";

interface Props {
  api: OriginsApi;
  repositories: RepositorySnapshot[];
  onAccepted: () => Promise<void> | void;
}

export default function ProcessTerminal({ api, repositories, onAccepted }: Props) {
  const [repositoryId, setRepositoryId] = useState("");
  const [executable, setExecutable] = useState("npm");
  const [argsText, setArgsText] = useState('["--version"]');
  const [cwd, setCwd] = useState(".");
  const [timeoutSeconds, setTimeoutSeconds] = useState(120);
  const [result, setResult] = useState<JsonRecord | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const active = repositories.find((repo) => repo.repository_id === repositoryId) ?? repositories[0];

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!active?.workspace_id || !active.worktree_root) return;
    setBusy(true); setError(""); setResult(null);
    try {
      const args = JSON.parse(argsText) as unknown;
      if (!Array.isArray(args) || args.some((value) => typeof value !== "string")) {
        throw new Error("Arguments must be a JSON array of strings.");
      }
      const envelope: JsonRecord = {
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
          cwd: cwd.trim() || ".",
          timeout_seconds: timeoutSeconds,
          max_output_bytes: 1024 * 1024,
        },
        created_at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
      };
      setResult(await api.runCommand(envelope));
      await onAccepted();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  }

  if (!repositories.length) return <div className="empty">Inspect a repository before starting a supervised process.</div>;

  return <div className="process-terminal">
    <div className="terminal-note">Non-interactive native process surface. It sends argv directly; no shell parser, stdin, secret injection, or generic Git execution is added.</div>
    <form onSubmit={submit}>
      <div className="terminal-grid">
        <label>Repository<select value={active?.repository_id ?? ""} onChange={(event) => setRepositoryId(event.target.value)}>{repositories.map((repo) => <option key={repo.repository_id} value={repo.repository_id}>{repo.worktree_root ?? repo.repository_id}</option>)}</select></label>
        <label>Executable<input value={executable} onChange={(event) => setExecutable(event.target.value)} required placeholder="npm, cargo, python…"/></label>
        <label>cwd<input value={cwd} onChange={(event) => setCwd(event.target.value)} required/></label>
        <label>Timeout seconds<input type="number" min={1} max={3600} value={timeoutSeconds} onChange={(event) => setTimeoutSeconds(Number(event.target.value))}/></label>
      </div>
      <label>argv JSON<textarea rows={4} value={argsText} onChange={(event) => setArgsText(event.target.value)} spellCheck={false}/></label>
      <button disabled={busy || !executable.trim()}>{busy ? "Submitting…" : "Run supervised process"}</button>
    </form>
    {error && <div className="banner error embedded">{error}</div>}
    {result && <pre className="json">{JSON.stringify(result, null, 2)}</pre>}
  </div>;
}
