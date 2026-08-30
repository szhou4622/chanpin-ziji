# Task Domain Model

The v2 engine now has a canonical Task vocabulary, a compatibility persistence/read bridge, a module dependency resolver and a pure execution-state transition boundary. The current production executor still lives in the existing runtime; the Task Scheduler has not yet taken execution ownership.

## Task vs Attempt

A **Task** is one durable unit of business work, for example parsing one source or generating one module result.

An **Attempt** is one execution attempt for that logical task. Provider/network retries must not be confused with a new business task.

This distinction is required for future request reconciliation and billing idempotency.

## Execution status

Canonical task execution states:

- `PENDING`
- `READY`
- `RUNNING`
- `WAITING_RETRY`
- `PAUSED`
- `SUCCEEDED`
- `FAILED`
- `CANCELLED`

Execution answers: **did the work run?**

## Result status

Canonical result states:

- `VALID`
- `STALE`
- `INSUFFICIENT`
- `INVALID`

Result answers: **can the output still be used for the current inputs?**

The axes are intentionally independent. A task may be `SUCCEEDED + STALE`: execution completed correctly, but a later source/instruction/dependency change invalidated the old business result.

`INSUFFICIENT` is a legitimate completed result. Missing required sources, no usable upstream result, or an evidence-supported “暂无分析” outcome may therefore be represented as `SUCCEEDED + INSUFFICIENT` rather than as execution failure.

## Canonical lifecycle boundary

New logical tasks are created through `createPendingTaskRecord()` and begin as `PENDING` with `attemptCount = 0`.

Execution status changes must go through `transitionTaskExecution()`. Scheduler/runtime code must not directly mutate `executionStatus`.

Allowed transitions are:

```text
PENDING ──→ READY ──→ RUNNING ──→ SUCCEEDED
   │          │           ├──────→ FAILED ──→ READY
   │          │           ├──────→ WAITING_RETRY ──→ READY
   │          │           ├──────→ PAUSED ──→ READY
   │          │           └──────→ CANCELLED
   │          ├───────────→ PAUSED / CANCELLED
   └──────────────────────→ PAUSED / CANCELLED

FAILED ─────→ CANCELLED
WAITING_RETRY → PAUSED / CANCELLED
PAUSED ─────→ CANCELLED
SUCCEEDED and CANCELLED are terminal.
```

The lifecycle reducer also enforces:

- `PENDING` cannot skip the scheduler claim boundary and jump directly to `RUNNING`;
- `READY` cannot jump directly to `SUCCEEDED`;
- state timestamps cannot move backwards relative to the current `updatedAt`;
- `WAITING_RETRY` requires a valid `retryAt` that is not earlier than the transition time;
- only `SUCCEEDED` may carry `resultStatus`, `resultFingerprint` or `outputRef`;
- `SUCCEEDED` must explicitly declare `VALID`, `INSUFFICIENT` or `INVALID`;
- `STALE` is not a completion result written by a new execution; it is created by later invalidation;
- attempt counting is not performed by the Task lifecycle reducer. It belongs to the future Attempt Manager.

## Reuse rule

A result may be reused only when:

1. execution is `SUCCEEDED`;
2. result is `VALID` or `INSUFFICIENT`;
3. the current input fingerprint exactly matches the task input fingerprint;
4. the required output payload still exists.

Timestamps are not an identity mechanism.

`INSUFFICIENT` is reusable for identical inputs because “the evidence is insufficient” is a valid business outcome and should not repeatedly consume model tokens.

## Dependency validity

A downstream task records dependency result fingerprints.

Example:

```text
M6
├ M2 result fingerprint
├ M4 result fingerprint
└ M5 result fingerprint
```

If any current dependency fingerprint differs, the old M6 result becomes `STALE` even if timestamps appear ordered correctly.

The active six-module dependency graph is resolved by the pure module dependency resolver rather than by a second hard-coded wave list.

## Invalidation

Invalidation preserves the old completed output identity:

```text
SUCCEEDED + VALID
        ↓ source/instruction/dependency change
SUCCEEDED + STALE
        ↓ replacement task succeeds
new result becomes current
```

The UI may therefore keep a clearly labelled historical/stale result while recomputation is underway.

## Attempt status

Attempt states include:

- `CREATED`
- `RUNNING`
- `UNKNOWN`
- `SUCCEEDED`
- `FAILED`
- `CANCELLED`

`UNKNOWN` is deliberate. A disconnected request is not automatically a failed request. Phase 2 will reconcile server request state before creating a replacement attempt.

## Legacy task journal compatibility

Existing `ProjectTaskSnapshot` records are projected deterministically:

- `complete` → `SUCCEEDED + VALID`
- `failed` → `FAILED`
- `interrupted` → `PAUSED`

Legacy inline output is preserved separately. Migration never invokes a model and does not reinterpret old output content.

Legacy attempt count is unknown, so compatibility projection uses `attemptCount = 0` as an explicit migration sentinel.

## Runtime authority bridge

Runtime completed/failed task mutations currently pass through compatibility adapters and may write both representations with the same `updatedAt`:

```text
runtime mutation
      ↓
compatibility adapter
   ↙             ↘
taskJournal     taskRecords
(payload)       (canonical state)
```

Active v2 resume/reuse decisions for source-clean batches and module results read through `readRuntimeTaskState()`:

```text
readRuntimeTaskState
      ↓
TaskRecord decides execution/result state
      +
taskJournal supplies legacy inline output payload
```

Current canonical result semantics include:

- normal completed module/source-clean result → `SUCCEEDED + VALID`;
- local or model evidence-insufficient module result → `SUCCEEDED + INSUFFICIENT`;
- failed task → `FAILED`;
- retry deletion removes the same task id from both representations.

`taskJournal` is no longer the active execution/result-state authority for these reuse decisions. It remains the compatibility payload carrier until Artifact/Blob output references replace inline output.

## Read bridge fallback rule

For a journal-backed task, canonical state is accepted only when it represents the same logical mutation as the payload carrier:

1. canonical record id matches the task id;
2. canonical `updatedAt` matches the corresponding journal entry.

If those conditions fail, the bridge deterministically projects the journal entry into a legacy-derived `TaskRecord`.

This is a compatibility/recovery rule, not a long-term merge strategy.

## Persistence trust boundary

Persisted `taskRecords` are strictly sanitized before restore.

There are now two persistence cases:

### Journal-backed tasks

For tasks that still carry legacy inline output, canonical metadata must match the same journal mutation before it can override the deterministic journal projection.

### Canonical-only non-success tasks

Scheduler states do not necessarily have a legacy journal payload. Therefore canonical-only records in non-success states may survive persistence after strict schema validation.

Important recovery rules:

- `PENDING`, `READY`, `WAITING_RETRY`, `PAUSED`, `FAILED` and `CANCELLED` may persist without a journal entry;
- persisted `RUNNING` is recovered as `PAUSED` because the process that owned that execution no longer exists after application restart;
- `retryAt` is preserved for `WAITING_RETRY`;
- canonical-only `SUCCEEDED` is rejected while completed output still depends on the legacy payload carrier.

The last rule prevents a corrupt or hand-edited metadata record from inventing a successful task with no trusted output. It can be relaxed only when Artifact/Blob `outputRef` becomes the authoritative completed-output contract.

## Storage boundary

`TaskRecord` stores task metadata and references, not large report/source/model text.

Storage split remains:

- business/task metadata → repository abstraction
- large artifacts → BlobStore
- observability → JSONL

No client SQLite dependency is introduced in this phase.

## Current module scheduler boundary

The active v2 module dependency resolver already owns:

- dependency graph validation;
- cycle/missing-dependency rejection;
- deterministic execution batches;
- transitive downstream retry/invalidation scope.

A dependency is currently an ordering dependency, not a requirement that the upstream result must be successful. `done`, `skipped` and `failed` upstream module states all count as settled for ordering, because downstream modules may continue with explicit missing-evidence context.

The existing runtime still launches the actual model work. The next safe step is to shadow the existing execution with canonical lifecycle states before allowing a new Scheduler to take execution ownership.

## Next migration boundary

The next task-domain step should be one-directional and low risk:

1. materialize active module Tasks as canonical `PENDING` records;
2. use the dependency resolver to promote eligible tasks to `READY`;
3. immediately before the existing executor starts a module, atomically transition `READY → RUNNING`;
4. map the existing real outcomes back to `SUCCEEDED / FAILED / PAUSED` through the lifecycle boundary;
5. keep the existing three-batch executor and concurrency behavior unchanged while shadow state is observed;
6. only after that is stable should Scheduler execution ownership replace the legacy orchestration loop.

This avoids introducing a second scheduler while still proving that canonical state describes the real execution faithfully.

## Not implemented yet

- real Attempt Manager / attempt counting
- Scheduler execution ownership
- Admission Engine
- Retry Policy / Failure Classifier
- automatic resume of recovered `PAUSED` tasks
- server request status/cancel/reconcile
- provider cancellation
- billing settlement changes
- full Artifact/Blob output-reference migration
- removal of legacy `taskJournal`
- SourceUnit/Evidence migration

Later phases must consume this task vocabulary rather than create parallel status systems.
