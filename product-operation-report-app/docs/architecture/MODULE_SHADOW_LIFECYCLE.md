# Module Shadow Lifecycle

Phase 1B introduces an observational canonical lifecycle for model-backed v2 module executions.

It does **not** own scheduling, retries, admission, cancellation transport, billing, or legacy reuse yet.

## Purpose

The current production module runner already performs real work, but its execution state is spread across:

- `moduleStates`
- legacy `taskJournal`
- `runModelRetry()`
- Electron request state
- server request/billing state

Before a future Scheduler can own execution, the canonical Task model must first prove that it can describe the real runtime without changing business behavior.

The shadow lifecycle therefore records the execution beside the current production path.

## Authority boundary

Current authority remains:

```text
existing module batches
        ↓
runModule()
        ↓
runModelRetry()
        ↓
legacy taskJournal / moduleStates
```

The shadow Task is observational metadata only:

```text
existing execution ───────────────→ production outcome
        │
        └── shadow observation ──→ TaskRecord + currentTaskByLogicalKey
```

A shadow bookkeeping failure must never prevent the real model request from starting or completing.

## First-slice coverage

This first shadow slice observes only a module execution that actually reaches a model request.

It does not invent RUNNING tasks for:

- exact result reuse
- targeted-retry retained outputs
- local source-sufficiency skips
- legacy benchmark compatibility skips

Those outcomes remain represented by the existing production state until the Scheduler owns the complete task graph.

## Identity

For a v2 module:

```text
logicalKey = <analysisSessionId>:module:v2:<moduleKey>
payloadKey = same stable legacy taskJournal key
TaskRecord.id = <logicalKey>@<immutable instance token>
```

The current index points from the stable logical slot to the immutable shadow Task instance.

The model/server request identity remains unchanged in this phase:

```text
taskKey          = legacy stable module key
billingRequestId = legacy stable module key
```

Changing server request identity is a later request-lifecycle phase.

## Execution mapping

When a real model execution begins:

```text
PENDING → READY → RUNNING
```

The same immutable Task then records one terminal observation:

```text
RUNNING → SUCCEEDED + VALID
RUNNING → SUCCEEDED + INSUFFICIENT
RUNNING → FAILED
RUNNING → CANCELLED
```

Examples:

- valid module output → `SUCCEEDED + VALID`
- model explicitly returns a legitimate no-analysis result → `SUCCEEDED + INSUFFICIENT`
- request failure / empty output → `FAILED`
- output remains structurally invalid after correction → `FAILED`
- explicit user stop → `CANCELLED`
- unhandled rejected Promise while the exact current shadow is still RUNNING → `FAILED`

## Retry semantics in this slice

`runModelRetry()` still owns transport/network retries internally.

The shadow Task does **not** emit `WAITING_RETRY` for those internal attempts yet. Doing so before an Attempt Manager exists would pretend that a transport retry is already a durable business-task retry.

Current rule:

- same-input module rerun after a shadow `FAILED/PAUSED/WAITING_RETRY` may resume the same immutable Task;
- after `SUCCEEDED/CANCELLED`, a new model run creates a new immutable Task instance;
- if input identity changes while an old nonterminal shadow exists, the old shadow is explicitly `CANCELLED` with `INPUT_CHANGED` before a replacement is created.

## Completed-task recovery

A canonical-only completed Task is not trusted after restart merely because metadata says `SUCCEEDED`.

A completed immutable shadow Task survives `reconcileTaskRecordMirror()` only when its `payloadKey` points to a real legacy payload proving the same completion:

1. payload exists;
2. payload status is `complete`;
3. payload kind maps to the same canonical Task kind;
4. payload `updatedAt` exactly matches canonical `updatedAt`;
5. when the canonical Task has an input fingerprint, payload fingerprint matches exactly.

Any mismatch drops the completed shadow Task. This keeps recovery fail-closed while the output still lives in the legacy journal rather than Artifact/Blob storage.

## Current-index limitation

During this observational phase, `currentTaskByLogicalKey` for modules describes the latest model-backed shadow execution, not every possible local business outcome.

For example, a later local source-insufficiency decision may complete through the legacy path without starting a new shadow Task.

Therefore no production scheduling or reuse decision may use the shadow current index yet.

The future Scheduler must first model local/reused/AI task outcomes consistently before current-index authority can move from observation to execution.

## Known divergence: model success vs persistence success

The existing production runner currently writes a successful module result and then awaits `saveLastProject()`.

If that post-success persistence call throws, the surrounding `Promise.allSettled()` path can classify the module as failed even though the model execution already succeeded.

The shadow lifecycle intentionally does not rewrite that behavior in this PR. It may therefore expose a temporary divergence:

```text
shadow execution = SUCCEEDED
legacy module path = FAILED because post-success persistence threw
```

Recovery remains safe because a later failed legacy payload no longer proves the completed shadow Task, so the completed shadow metadata is dropped after restart.

This persistence/error-classification conflation should be fixed as a separate small change before Scheduler ownership expands.

## Explicitly not implemented

- Scheduler execution ownership
- Admission Engine
- Attempt Manager / real attempt counting
- durable `WAITING_RETRY` decisions
- server request status / cancel / reconcile
- provider cancellation
- 409 request-lifecycle repair
- billing identity changes
- actual-usage billing changes
- module dependency ownership by canonical current tasks
- local/cache-result Task instances for every module outcome
- Artifact/Blob output-reference migration
- removal of legacy `taskJournal`

The next safe step is to resolve execution-success vs persistence-failure semantics, then continue toward Scheduler/Admission ownership using the observed canonical lifecycle rather than creating another status system.
