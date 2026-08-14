import { useEffect, useState } from "react";
import type { OriginsApi, RepositoryFileEntry, RepositoryFileSnapshot } from "./api";

interface Props {
  api: OriginsApi;
  repositoryId: string;
}

function parentPath(path: string): string {
  const parts = path.split("/").filter(Boolean);
  parts.pop();
  return parts.join("/");
}

export default function RepositoryEditor({ api, repositoryId }: Props) {
  const [directory, setDirectory] = useState("");
  const [entries, setEntries] = useState<RepositoryFileEntry[]>([]);
  const [opened, setOpened] = useState<RepositoryFileSnapshot | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");

  async function loadDirectory(next: string) {
    setBusy(true); setError(""); setSaved("");
    try {
      const listing = await api.repositoryFiles(repositoryId, next);
      setDirectory(listing.path);
      setEntries(listing.entries);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  }

  async function openFile(path: string) {
    setBusy(true); setError(""); setSaved("");
    try {
      const snapshot = await api.repositoryFile(repositoryId, path);
      setOpened(snapshot);
      setDraft(snapshot.text ?? "");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  }

  async function saveFile() {
    if (!opened?.editable) return;
    setBusy(true); setError(""); setSaved("");
    try {
      await api.writeRepositoryFile(repositoryId, opened.path, draft, opened.sha256);
      const refreshed = await api.repositoryFile(repositoryId, opened.path);
      setOpened(refreshed);
      setDraft(refreshed.text ?? "");
      setSaved(`Saved ${refreshed.path} · ${refreshed.sha256.slice(0, 12)}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  }

  useEffect(() => {
    setOpened(null); setDraft(""); setDirectory(""); setEntries([]);
    void loadDirectory("");
    // api is recreated only when connection parameters change; repositoryId is the active scope.
  }, [api, repositoryId]);

  return <div className="editor-shell">
    <div className="file-browser">
      <div className="browser-head"><b>Files</b><span>{directory || "/"}</span></div>
      {directory && <button className="file-entry" onClick={() => void loadDirectory(parentPath(directory))} disabled={busy}>↰ ..</button>}
      {entries.map((entry) => <button
        className="file-entry"
        key={entry.path}
        disabled={busy || entry.kind === "other"}
        onClick={() => entry.kind === "directory" ? void loadDirectory(entry.path) : void openFile(entry.path)}
      >
        <span>{entry.kind === "directory" ? "▸" : "·"} {entry.name}</span>
        <small>{entry.kind === "file" && typeof entry.bytes === "number" ? `${entry.bytes} B` : entry.kind}</small>
      </button>)}
      {!entries.length && !busy && <div className="empty compact">No visible entries.</div>}
    </div>
    <div className="editor-pane">
      {opened ? <>
        <div className="editor-head"><div><b>{opened.path}</b><small>{opened.bytes} bytes · {opened.sha256.slice(0, 16)}</small></div><button onClick={() => void saveFile()} disabled={busy || !opened.editable || draft === (opened.text ?? "")}>Save</button></div>
        {opened.editable ? <textarea className="code-editor" value={draft} onChange={(event) => setDraft(event.target.value)} spellCheck={false}/> : <div className="empty">Binary/non-UTF-8 files are evidence-only in this editor.</div>}
      </> : <div className="empty">Select a UTF-8 repository file to open it.</div>}
      {error && <div className="banner error embedded">{error}</div>}
      {saved && <div className="banner success embedded">{saved}</div>}
    </div>
  </div>;
}
