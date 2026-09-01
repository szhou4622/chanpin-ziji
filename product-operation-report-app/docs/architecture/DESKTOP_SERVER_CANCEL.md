# Desktop to Server Cancellation Bridge

## Scope

This Phase 2 change connects an explicit desktop cancellation to the server request lifecycle introduced by `REQUEST_LIFECYCLE_FOUNDATION.md`.

It intentionally does **not** implement automatic disconnect/409/restart reconciliation yet.

## Old behavior

Before this bridge, the renderer and Electron main process could abort the local HTTP/SSE transport, but the business server might continue processing the provider request. The user could therefore see a stopped task while the server still held a `running` request.

## New main-process boundary

`ChatRequestRegistry` remains a transport-only registry for Electron request ownership and local `AbortController` instances.

A separate `ProxyRequestTracker` now tracks only managed-proxy lifecycle identity:

```text
root chat request id
→ renderer owner id
→ logical taskKey
→ current concrete server request id
```

The current concrete request may be the root UUID or a model-fallback request such as `:fallback:1`.

Keeping this separate prevents server business lifecycle concerns from turning `ChatRequestRegistry` into a scheduler or durable task store.

## Explicit stop

When the renderer sends `chat:abort`:

1. Electron main snapshots the owner-scoped proxy request record;
2. the local `AbortController` is aborted immediately;
3. for managed proxy mode, Electron main also sends a best-effort server cancellation;
4. if the current concrete request id is known, that id is cancelled first;
5. if that id is already absent/terminal, the control plane falls back to `GET /requests/active/{taskKey}` and cancels any currently running request for that owned logical task.

The renderer does not receive or control the proxy session token and does not call lifecycle endpoints directly.

## Window and renderer cleanup

The same server-cancel propagation is attempted when:

- the user confirms “stop task and exit”;
- the renderer process disappears;
- the window closes;
- the application enters `before-quit`.

These shutdown paths are **best effort**. The existing application has a hard-exit watchdog and operating systems may terminate a process before an asynchronous control-plane request completes. A future `ShutdownCoordinator` may provide bounded awaited shutdown semantics.

Explicit stop while the application remains alive is the stronger path.

## Fallback race protection

A single root chat request may execute multiple model/provider attempts. Before every fallback attempt, Electron main checks the shared local abort signal again.

If the user stopped the task after one attempt ended but before the fallback callback begins, the next provider attempt is not started.

This preserves the rule:

```text
user stop
→ no new fallback/provider request may begin afterward
```

## Control-plane API ownership

`aiProxy.ts` owns request lifecycle HTTP calls because it already owns:

- proxy session creation;
- bearer-token storage;
- 401 token refresh;
- short control-plane request timeout.

Lifecycle helpers use the same session boundary for:

- request state;
- active requests by task key;
- request cancellation.

Task keys and request IDs are validated locally against the same safe identifier alphabets enforced by the server before being inserted into request paths. In particular, the active-task path uses the validated raw task key; it must not turn `:` into `%3A` and then rely on the server to decode an unsafe path.

## Failure semantics

Server cancellation is deliberately best-effort from the local stop handler:

- local stop must not be blocked by a temporarily unavailable control plane;
- failure to notify the server is logged in the main process;
- it is **not** treated as proof that the server stopped;
- automatic reconciliation of that uncertain state is the next Phase 2 change.

The client therefore must not infer a terminal server state from local transport cancellation alone.

## Still not implemented

This bridge does not yet:

- convert network disconnect into an `UNKNOWN / RECONCILE` lifecycle;
- query active requests before every retry;
- intercept a same-task `409` and wait/cancel/reconcile the actual server request;
- reconcile tasks after an application restart;
- persist concrete server request IDs as durable business state;
- remove the server's 409 duplicate-protection guard;
- make the new tracker a scheduler or source of truth for analysis Tasks.

Those behaviors belong to the next desktop request-reconciliation change.

## Non-regression rules

- `ChatRequestRegistry` stays owner-scoped and transport-only.
- `ProxyRequestTracker` cannot cross renderer owner IDs.
- managed proxy request IDs accept only canonical UUIDs plus supported fallback suffixes.
- task keys accept only the server-compatible safe alphabet.
- lifecycle parsers retain only bounded operational metadata.
- a parent/local abort prevents later model fallback attempts.
- renderer code never receives proxy bearer tokens or direct lifecycle endpoint access.
- server-side verified-usage-only billing remains authoritative and unchanged by this desktop bridge.
