# Managed Proxy Request Reconciliation

## Scope

This document defines the Phase 2 desktop-side reconciliation rule for managed model requests.

The server request lifecycle and desktop cancellation bridge already exist. This layer closes the remaining gap where a desktop transport failure can lose the response stream while the business server still has the logical task running.

## Problem

The old retry path behaved like this:

```text
managed request starts
→ desktop HTTP/SSE transport fails or times out
→ renderer receives an error
→ renderer retry creates a new root UUID
→ server may still have the prior taskKey running
→ new request collides with the server 409 duplicate-task guard
```

A 409 is therefore not a reason to remove the server guard. It is evidence that the desktop and server disagree about the lifecycle of the prior logical task.

## Rule

Before every new managed-proxy upstream submission, Electron main must prove that the same logical `taskKey` has no running server request.

```text
new root request
→ local atomic taskKey admission
→ GET /requests/active/{taskKey}
→ no active request
   → submit new model attempt
→ detached active request exists
   → request cancellation
   → poll active state until server proves it is no longer running
   → only then submit the new attempt
→ lifecycle state cannot be confirmed
   → fail closed; do not submit
→ prior request remains running past bounded reconcile window
   → fail closed; do not submit
```

## Local versus server ownership

There are two different duplicate protections and they must not be merged.

### Local process protection

`ProxyRequestTracker.claim()` atomically rejects a second in-process root request with the same `taskKey`.

This prevents a second renderer/task from cancelling a healthy request that this same desktop process still owns.

### Server detached-request reconciliation

Only after local admission succeeds does Electron main query the business server for active requests with the same `taskKey`.

Those requests are treated as detached from the current root request. Because the server intentionally does not persist model output, the current renderer cannot safely reattach to that old stream. The old request is cancelled and must become non-running before another provider submission is allowed.

## Fail-closed behavior

The following conditions must never be interpreted as permission to submit a new provider request:

- active-request lookup fails or times out;
- cancellation fails;
- a running request remains after the bounded reconciliation window;
- the active-task endpoint returns metadata whose `taskKey` differs from the task being reconciled;
- the user aborts while reconciliation is running.

In these cases no new upstream request is created.

## Retry behavior

Renderer retries remain bounded. A retry creates a new root request, but that new root must pass Electron main admission and server reconciliation before any model call can start.

A server `409` is mapped to a lifecycle-conflict user message and is retryable only because the following retry now goes through this safe reconciliation gate.

Network failures and 5xx responses keep their bounded retry behavior; they cannot bypass reconciliation in managed-proxy mode.

## Relationship to billing

This layer does not calculate user charges.

Billing remains server-authoritative:

- reservation/estimates are admission controls only;
- verified provider usage is the only basis for final user charging;
- cancelled requests with verified usage charge only that real usage;
- missing/unrecoverable usage does not become an estimated final user charge.

Reconciliation exists to prevent overlapping nonterminal attempts and unnecessary provider spend, not to replace server settlement.

## Request identity

The layers remain distinct:

- `taskKey` — stable logical task identity used for duplicate protection and reconciliation;
- root request UUID — one renderer/main transport run;
- concrete request ID — one actual model/fallback submission;
- billing request ID — logical billing identity already supplied by the task context.

A new root UUID never proves that an old logical task is gone.

## Non-regression invariants

Tests must preserve at least the following:

1. no active server request → submission can proceed;
2. detached running request → cancellation is requested and submission waits;
3. detached request becomes terminal → new submission may proceed;
4. detached request stays running → no new submission;
5. lifecycle API unavailable → no new submission;
6. mismatched taskKey in lifecycle response → no new submission;
7. user abort during reconciliation → no new submission;
8. two in-process roots cannot claim the same taskKey;
9. server 409 remains a duplicate-spend safety guard;
10. renderer retry of a lifecycle conflict re-enters normal admission rather than bypassing it.

## Remaining limitation

The canonical task journal does not yet persist an explicit `UNKNOWN / RECONCILING` execution state for every transport-loss event. Operational safety is already enforced by the pre-submission gate, while a later task-state refinement may make that transient state visible in the durable task model and UI.
