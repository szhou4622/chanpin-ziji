# Task Domain Model

Phase 1A introduces the canonical task vocabulary and a compatibility persistence/read bridge. It does **not** replace the current scheduler/request pipeline yet.

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

These axes are intentionally independent. A task may be `SUCCEEDED + STALE`: execution completed correctly, but a later source/instruction/dependency change invalidated the business result.

## Reuse rule

A result may be reused only when:

1. execution is `SUCCEEDED`;
2. result is `VALID` or `INSUFFICIENT`;
3. the current input fingerprint exactly matches the task input fingerprint.

Timestamps are not an identity mechanism.

`INSUFFICIENT` is reusable for identical inputs because “the evidence is insufficient” is a legitimate result and should not repeatedly consume model tokens.

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

## Invalidation

Invalidation must preserve the old completed output identity.

```text
SUCCEEDED + VALID
        ↓ source/instruction/dependency change
SUCCEEDED + STALE
        ↓ replacement task succeeds
new result becomes current
```

The UI can therefore keep showing a clearly labelled historical/stale result while recomputation is underway.

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

Legacy attempt count is unknown, so the compatibility projection uses `attemptCount = 0` as an explicit migration sentinel; the later Attempt Manager will count real attempts.

## Phase 1A runtime authority bridge

Runtime task mutations pass through one adapter and write both representations with the same `updatedAt`:

```text
runtime mutation
      ↓
Task Journal Adapter
   ↙             ↘
taskJournal     taskRecords
(payload)       (canonical state)
```

The active v2 resume/reuse decisions for source-clean batches and module results now read through `readRuntimeTaskState()`:

```text
readRuntimeTaskState
      ↓
TaskRecord decides execution/result state
      +
taskJournal supplies legacy inline output payload
```

Current canonical state semantics include:

- normal completed module/source-clean result → `SUCCEEDED + VALID`;
- evidence-supported “暂无分析” module result → `SUCCEEDED + INSUFFICIENT`;
- failed task → canonical `FAILED`;
- retry deletion removes the same task id from both representations.

A source-clean batch is reusable only when canonical state is `SUCCEEDED + VALID` and its journal payload exists.

A module result is reusable only when canonical state is `SUCCEEDED + VALID` or `SUCCEEDED + INSUFFICIENT`, its input fingerprint matches the current module input, and its journal payload exists. `STALE`, `INVALID`, `FAILED`, `PAUSED` and other non-reusable states cannot be revived merely because old output text remains in the journal.

`taskJournal` is therefore no longer the execution/result-state authority for these active runtime reuse decisions. It remains the compatibility payload carrier and is still used by load-time legacy repair/migration paths until artifact/output storage is separated.

The two representations must not become independent competing writers.

## Read bridge fallback rule

Canonical state is accepted by the runtime read bridge only when it represents the exact same mutation as the payload carrier:

1. the canonical record id matches the task id;
2. canonical `updatedAt` exactly matches the corresponding journal entry.

If those conditions are not met, the bridge deterministically projects the journal entry into a legacy-derived `TaskRecord`.

This fallback is a compatibility/recovery rule, not a long-term merge strategy. It prevents stale or partially migrated canonical metadata from blocking old projects while the transition is incomplete.

## Persistence trust boundary

Persisted `taskRecords` are strictly sanitized before restore.

A persisted canonical record is accepted only when:

1. its schema, id, task kind, statuses, timestamps, dependency structure and bounded string fields are valid;
2. its id exactly matches the containing record key;
3. its `updatedAt` exactly matches the corresponding sanitized `taskJournal` entry.

If any check fails, the persisted canonical record is discarded and that task safely falls back to a deterministic journal projection.

This means a corrupt, stale or hand-edited canonical record cannot override recoverable project state. It also preserves canonical-only result semantics such as `INSUFFICIENT` when both sides came from the same runtime mutation.

Load-time legacy recovery can still repair or delete journal entries. After those corrections, the renderer reconciles canonical metadata again, so repaired journal state cannot retain an older mismatched canonical record.

## Storage boundary

`TaskRecord` stores task metadata and references (`outputRef`), not large report/source/model text. The current bridge does not copy legacy model output into canonical task metadata.

Future storage split remains:

- business/task metadata → repository abstraction
- large artifacts → BlobStore
- observability → JSONL

Phase 1A does not introduce SQLite.

## Next migration boundary

The next task-domain work must **not** delete `taskJournal` or move large output text into `TaskRecord`.

The safe next boundary is to introduce the runtime execution layer around this canonical vocabulary:

1. Scheduler / Dependency Resolver decides which canonical task may run;
2. Admission Engine checks authorization, capability, concurrency and resource gates;
3. Attempt Manager separates a logical Task from transport/provider attempts;
4. Failure Classifier + Retry Policy drive `WAITING_RETRY` rather than ad-hoc retry branches;
5. legacy journal remains a payload compatibility layer until Artifact/Blob references replace inline output.

This keeps the migration one-directional: new execution logic consumes canonical task state instead of creating another status system.

## Not implemented in Phase 1A

- real Attempt Manager / attempt counting
- Scheduler / Dependency Resolver
- Admission Engine
- Retry Policy
- Failure Classifier
- automatic crash resume from nonterminal canonical tasks
- server request status/cancel/reconcile
- provider cancellation
- billing settlement changes
- full Artifact/Blob output-reference migration
- removal of legacy `taskJournal`
- SourceUnit/Evidence migration

Those are later phases and must consume this task vocabulary rather than create parallel status systems.
