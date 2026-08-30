# Request Protocol Target

Phase 0 documents this protocol; it does not implement the server lifecycle APIs.

## Identifiers

Future request lifecycle must distinguish:

- Analysis ID
- Source ID
- Artifact ID
- Logical Job ID
- Attempt ID
- Request ID
- Billing Logical ID

A retry/fallback is a new Attempt/Request of the same Logical Job. Billing identity must remain stable across automatic retries for one billable logical task.

## Target lifecycle

```text
READY
 -> REQUEST_CREATED
 -> RUNNING
 -> SUCCEEDED | FAILED | CANCELLED
```

At most one non-terminal attempt may exist for one logical job/model route unless an explicit protocol permits otherwise.

## Current disconnect problem

Current desktop retry can create a fresh request id while the server still has the prior same task key/model in `running`. The server then returns 409 for the replacement request. Main-process local abort does not currently guarantee server/provider cancellation.

## Required recovery protocol

```text
transport disconnect
 -> local state UNKNOWN
 -> RECONCILE
 -> query server request state
 -> cancel/settle prior attempt when required
 -> wait until prior attempt is terminal
 -> create replacement attempt
```

Do not overlap replacement attempts while the old attempt remains non-terminal.

## User stop

Target behavior:

1. stop launching new jobs;
2. request server/provider cancellation of active attempts;
3. preserve completed results;
4. settle verified provider usage idempotently;
5. leave unfinished jobs resumable.

## Billing separation

Request execution state and billing settlement state are separate. Estimate may be used for planning/reservation, but final user charge must be based on verified provider usage. If usage cannot be proven, do not convert an estimate into a final user charge.

## Phase 2 APIs

Expected control-plane endpoints include equivalents of:

- request status
- request cancel
- reconciliation

Exact paths are intentionally not fixed in Phase 0.
