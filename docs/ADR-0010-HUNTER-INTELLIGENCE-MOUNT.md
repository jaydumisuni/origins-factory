# ADR-0010 — Hunter Intelligence Mount v1

**Status:** ACCEPTED for implementation and challenge
**Date:** 2026-08-07
**Depends on:** ADR-0001 through ADR-0009
**External authority:** `jaydumisuni/hunter` `master`

## Purpose

Mount Hunter's current owner intelligence/session contract into Origins without copying Hunter's controller, provider router, memory engine, action routes, GitHub routes, or local executor.

```text
Origins Workspace
→ Python Hunter semantic adapter
→ authenticated local originsd API
→ narrow Rust Hunter transport
→ Hunter owner-authenticated API
→ Hunter response/session authority
```

Origins remains useful with the Hunter mount disabled. A model/provider is an amplifier, not a prerequisite for the mechanical Workspace.

## Recovered Hunter authority

Current `hunter/master` proves:

- production Worker root: `cloudflare/hunter-api-worker`;
- deployed Worker: `hunter-api-worker` on `hunter.thetechguyds.com`;
- current wrapper entrypoint delegates non-UI traffic to the Worker;
- Auth V2 accepts a bearer token or the `hunter_token` HttpOnly cookie;
- `/api/auth/v2/session` returns verified identity;
- approved owner/admin Core is exposed through `/core/status` and `/core/chat`;
- `/core/providers/status` is read-only provider visibility;
- verified-owner chat continuity is exposed through `/chat/save`, `/chat/list`, and `/chat/load`;
- `/api/system/version` exposes public-safe deployment identity;
- cloud chat namespaces are derived from verified account identity;
- current Core response remains OpenAI-compatible and identifies `model`, `provider`, and assistant content.

The owner Core route is preferred over public `/assistant/chat` and over UI compatibility aliases because it explicitly requires approved owner/admin identity and fixes context to `hunter_core_chat`.

## Ownership

Hunter owns:

- reasoning identity and system context;
- provider/model routing;
- conversation/chat semantic content;
- owner authentication semantics;
- Hunter memory/learning semantics;
- Hunter action/tool policies.

Origins owns:

- Workspace identity;
- mechanical network transport boundary;
- local secret isolation;
- bounded transport evidence;
- mapping a Workspace conversation to a Hunter chat session;
- presenting Hunter's response/provider/model state;
- deciding which Origins capability is invoked after semantic planning.

Origins does **not** copy Hunter's provider router or treat Hunter's GitHub/action routes as ambient tools.

## Transport boundary

Python/UI may not call Hunter directly.

`originsd` adds a Hunter-specific transport with no arbitrary URL method. Configuration is process-local:

```text
ORIGINS_HUNTER_URL
ORIGINS_HUNTER_TOKEN
```

Rules:

- production base must use HTTPS;
- loopback HTTP is allowed only for controlled local/CI fixtures;
- URL credentials/fragments are rejected;
- token is never returned to clients, stored in SQLite, written to journal payloads, or placed in argv;
- transport allowlists exact Hunter operations rather than arbitrary paths;
- redirects outside the configured Hunter origin are not accepted;
- response body is bounded before Python receives it;
- each request returns a compact transport receipt with operation, HTTP status, byte count, SHA-256, and timestamp/request ID;
- the permanent journal stores only transport metadata/digests, never Hunter chat bodies or tokens.

## Allowed Hunter operations

V1 allowlist:

```text
version          GET  /api/system/version
session          GET  /api/auth/v2/session
core_status      GET  /core/status
providers_status GET  /core/providers/status
chat_list        GET  /chat/list?limit=<bounded>
chat_load        GET  /chat/load?id=<safe-id>
chat_save        POST /chat/save
core_chat        POST /core/chat
```

No login/password/admin/action/GitHub/WhatsApp/email/device endpoint is available through this transport.

## Authentication gate

The Python mount doctor must prove, through the Rust transport:

1. Worker version endpoint is reachable and identifies `hunter-api-worker`;
2. Auth V2 session is authenticated;
3. identity role is `owner_admin`;
4. identity status is `approved`;
5. Core status returns `hunter_core_chat`.

Any failure blocks semantic chat. Origins does not fall back to the public/customer assistant.

## Conversation continuity

Hunter remains the semantic conversation owner. Origins does not duplicate complete chat history into SQLite.

A Hunter chat session used by Origins has a Workspace-scoped ID:

```text
origins-<workspace-id>-<thread-id>
```

V1 defaults to thread `main`. Thread IDs are sanitized and bounded.

Turn flow:

```text
Workspace ID
→ Hunter doctor/auth gate
→ load Hunter session if present
→ append current user turn in-memory
→ send bounded recent messages to /core/chat
→ validate OpenAI-compatible Hunter response
→ append assistant turn
→ save session through /chat/save
→ return compact turn receipt
```

If Hunter reports `server_newer` during save, Origins fails with a conversation conflict and requires reload; it never silently overwrites the newer semantic record.

## Context window

The current Hunter owner UI sends the most recent 12 messages to its online chat endpoint. V1 follows that proven bounded pattern for the Core request. Full retained semantic history remains in Hunter's chat session, while each inference request uses the latest 12 messages.

## Turn receipt

The Python adapter returns a compact receipt containing:

- Workspace ID;
- Hunter session ID;
- Hunter deployment identity when available;
- provider and model reported by Hunter;
- response SHA-256;
- transport request IDs/digests;
- saved/conflict status;
- canonical receipt SHA-256.

Raw bearer token is never present. Full conversation bodies remain in Hunter's semantic session rather than Origins' permanent journal.

## Provider/model policy

V1 does not add an Origins-owned model selector. `/core/providers/status` may be surfaced read-only, but provider/model choice remains Hunter-owned until the owning Hunter provider contract is recovered and explicitly mounted.

This prevents Origins from becoming a second provider router.

## Failure behavior

- missing Hunter configuration → mount disabled, Origins remains mechanically useful;
- unauthenticated/guest Hunter session → fail closed;
- non-owner/unapproved identity → fail closed;
- Hunter unavailable/provider failure → preserve transport evidence and return an honest unavailable result;
- malformed Hunter completion → fail closed;
- conversation save conflict → reload required, no overwrite;
- optional Hunter failure must not corrupt Origins Workspace/Repository/Session state.

## Proof requirements

Before promotion:

1. Rust transport rejects arbitrary paths and non-HTTPS non-loopback targets;
2. token never appears in local API responses or journal evidence;
3. Python source has no direct outbound HTTP implementation to Hunter;
4. doctor blocks guest/non-owner/unapproved sessions;
5. doctor requires `hunter_core_chat` Core status;
6. provider status is read-only only;
7. fixture Core chat returns provider/model/content through the actual Rust transport;
8. Workspace-scoped Hunter session load/save works;
9. only the last 12 messages are sent for inference while Hunter retains full saved session;
10. `server_newer` causes conflict rather than overwrite;
11. response/transport/turn receipts have deterministic SHA-256 evidence;
12. hosted proof runs a controlled Hunter fixture server plus real originsd;
13. every ADR-0002 through ADR-0009 proof remains green;
14. actual Hunter production connectivity is not claimed unless separately proven with a real owner token.

## Explicit non-claims

V1 does not provide or claim:

- automatic Hunter login or credential storage;
- production Hunter owner-token proof in CI;
- direct UI-to-Hunter network access;
- direct Python-to-Hunter network access;
- arbitrary Hunter API proxying;
- Hunter action/GitHub/email/WhatsApp execution through this mount;
- an Origins-owned provider/model router;
- AgentOps semantic persistence completion backend;
- React Workspace UI;
- PTY functionality;
- Ptah integration.
