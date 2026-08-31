# Request Lifecycle Foundation

## Scope

This document defines the Phase 2 server-side request lifecycle foundation for managed model requests.

This phase changes the business proxy and its billing semantics. It does **not** yet make the desktop client authoritative over server request reconciliation. Electron/main/preload integration is a separate follow-up.

## Why this exists

Before this foundation, stopping a request in the desktop only aborted the local HTTP/SSE connection. The business proxy could detect that the client connection was gone, but the provider stream could continue running in the background. A later retry of the same logical task could therefore hit the existing same-task `409` guard while the detached request was still `running`.

The server now has an explicit lifecycle surface so the desktop can reconcile the real server state instead of guessing from local transport state.

## Public lifecycle endpoints

The business proxy exposes the following authenticated endpoints under the existing product-operation-report API prefix:

- `GET /requests/{requestId}` — read one owned request's lifecycle metadata.
- `GET /requests/active/{taskKey}` — discover currently running requests for an owned logical task when the prior concrete request ID is unknown.
- `POST /requests/{requestId}/cancel` — durably request cancellation of one owned running request.

Nginx explicitly proxies the `/requests/` subtree. Unknown business-proxy routes remain fail-closed with `404`.

## Ownership and privacy

Lifecycle reads and cancellation are scoped to all of:

- application name;
- activation-code identity (`code_id`);
- current machine identity (`machine_code`).

A request that does not belong to the current activation and machine is returned as not found. The active-task lookup is subject to the same ownership boundary.

Lifecycle responses expose only operational metadata such as request ID, task key/type, model, attempt, status, timestamps, cancellation intent, upstream-submitted flag and usage-source classification.

The proxy still does not persist or return user prompts, uploaded source material, images or model output through these lifecycle APIs.

## Cancellation semantics

`POST /requests/{requestId}/cancel` is idempotent.

For a running request it records:

- `cancel_requested = 1`;
- `cancel_requested_at = <timestamp>`.

This is a **cancellation intent**, not a fake terminal state. The request remains `running` until the provider-processing path actually observes cancellation and settles the request.

Provider streaming now cooperatively polls the durable cancellation flag. When cancellation is observed:

1. no new provider request is opened if cancellation was already requested;
2. an already-open upstream response is actively closed;
3. the proxy stops forwarding/reading the request as a normal success path;
4. the request settles with an `aborted` business status.

### Blocking-open limitation

Python `urllib` cannot synchronously kill an in-progress blocking `urlopen()` while it is still waiting for provider response headers.

If cancellation arrives in that narrow phase, the public request thread can stop waiting for normal completion, and the provider worker closes the upstream response immediately when the blocking open returns. This foundation must therefore not promise instantaneous physical provider termination before an upstream response object exists.

A future provider adapter may replace this transport with one that offers stronger cancellation primitives.

## Verified-usage-only final billing

Admission estimates and reservations remain necessary to protect wallet balance and the daily safety cap. They are **not final billing evidence**.

Final user billing now follows this rule:

- verified provider usage available → settle using real provider input/output/cache usage;
- no verified provider usage → user charge is `0`, release the reservation;
- process restart with an in-flight request but no recoverable provider usage receipt → mark interrupted and release the reservation rather than estimating a user charge.

The platform absorbs provider cost that cannot be proven from provider usage instead of converting an estimate into a user debit.

Cancellation with real provider usage is not automatically free: if the provider returned verifiable usage before cancellation settled, the request is charged only for that verified usage.

Settlement remains idempotent and the existing wallet/ledger transaction boundaries remain in place.

## Relation to the existing 409 guard

The existing same-task duplicate guard remains intentional:

```text
same activation + taskKey + model + running request
→ second upstream submission is rejected with 409
```

Do **not** remove this guard to make retries appear to work. It prevents overlapping nonterminal attempts and duplicate spend.

The new `GET /requests/active/{taskKey}` endpoint exists specifically so the desktop can handle a future `409` by discovering the real running request, reconciling its status, waiting or cancelling it, and only then starting another attempt.

## What is not implemented in this phase

The desktop still does not yet:

- call server `POST /requests/{requestId}/cancel` from `chat:abort`;
- query request status after a disconnect;
- query active requests by task key after restart/409;
- represent transport loss as `UNKNOWN → RECONCILE`;
- prevent every retry from starting until server reconciliation completes.

Those behaviors belong to the next Phase 2 desktop reconciliation change.

## CI and non-regression

Server proxy tests are now a permanent `Daily CI` job in addition to the existing desktop quality and Windows Electron regression jobs.

The lifecycle regression suite locks at least these invariants:

- request state/cancel cannot cross activation or machine ownership;
- cancellation is idempotent;
- terminal requests are not rewritten by a later cancel call;
- cancellation before provider open prevents a new upstream submission;
- verified provider usage is the only token-usage basis for final user billing;
- missing usage releases reservations without estimate-charging the user;
- interrupted unverified requests are released on process recovery;
- active request lookup can recover a running request from `taskKey` without a prior concrete request ID;
- active lookup cannot see another activation/machine's requests;
- unsafe active-task paths are rejected;
- existing duplicate-request, wallet, daily-cap, ProviderKeyring, search and ledger regressions remain green.
