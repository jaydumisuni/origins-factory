import { FormEvent, useMemo, useState } from "react";
import type { OriginsApi } from "./api";
import type { JsonRecord } from "./model";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

interface Props {
  api: OriginsApi;
  configured: boolean;
  workspaceIds: string[];
}

function extractAssistantText(result: JsonRecord): string {
  const body = result.body;
  if (typeof body === "string") return body;
  if (!body || typeof body !== "object") return JSON.stringify(result, null, 2);
  const record = body as JsonRecord;
  for (const key of ["response", "content", "text", "answer"]) {
    if (typeof record[key] === "string" && record[key]) return record[key] as string;
  }
  const message = record.message;
  if (message && typeof message === "object" && typeof (message as JsonRecord).content === "string") {
    return (message as JsonRecord).content as string;
  }
  const choices = record.choices;
  if (Array.isArray(choices) && choices[0] && typeof choices[0] === "object") {
    const choice = choices[0] as JsonRecord;
    const choiceMessage = choice.message;
    if (choiceMessage && typeof choiceMessage === "object" && typeof (choiceMessage as JsonRecord).content === "string") {
      return (choiceMessage as JsonRecord).content as string;
    }
    if (typeof choice.text === "string") return choice.text;
  }
  return JSON.stringify(body, null, 2);
}

export default function HunterConversation({ api, configured, workspaceIds }: Props) {
  const uniqueWorkspaceIds = useMemo(() => [...new Set(workspaceIds.filter(Boolean))], [workspaceIds]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const activeWorkspace = workspaceId || uniqueWorkspaceIds[0] || "";

  async function submit(event: FormEvent) {
    event.preventDefault();
    const content = input.trim();
    if (!content || !activeWorkspace || busy) return;
    const nextMessages = [...messages, { role: "user", content } as ChatMessage];
    setMessages(nextMessages);
    setInput(""); setBusy(true); setError("");
    try {
      const bounded = nextMessages.slice(-12).map((message) => ({ role: message.role, content: message.content }));
      const result = await api.hunterRequest(activeWorkspace, "core_chat", { messages: bounded });
      setMessages((current) => [...current, { role: "assistant", content: extractAssistantText(result) }]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  }

  if (!configured) {
    return <div className="banner warn embedded">Hunter transport is not configured. Origins remains usable model-free; no synthetic assistant response is substituted.</div>;
  }
  if (!uniqueWorkspaceIds.length) {
    return <div className="banner warn embedded">Create or inspect a repository Workspace before starting Hunter conversation.</div>;
  }

  return <div className="chat-shell">
    <div className="chat-toolbar"><label>Workspace<select value={activeWorkspace} onChange={(event) => setWorkspaceId(event.target.value)}>{uniqueWorkspaceIds.map((id) => <option key={id}>{id}</option>)}</select></label><button className="secondary" onClick={() => setMessages([])} disabled={busy || !messages.length}>Clear local view</button></div>
    <div className="chat-log">
      {messages.length ? messages.map((message, index) => <div className={`chat-message ${message.role}`} key={`${message.role}-${index}`}><b>{message.role === "user" ? "You" : "Hunter"}</b><div>{message.content}</div></div>) : <div className="empty">Hunter is mounted through the Origins transport. Conversation state shown here is client-local until Phase 4 durable Operation/chat mounting is accepted.</div>}
      {busy && <div className="chat-message assistant"><b>Hunter</b><div>Working…</div></div>}
    </div>
    {error && <div className="banner error embedded">{error}</div>}
    <form className="chat-compose" onSubmit={submit}><textarea rows={3} value={input} onChange={(event) => setInput(event.target.value)} placeholder="Ask Hunter within this Workspace…"/><button disabled={busy || !input.trim()}>Send</button></form>
  </div>;
}
