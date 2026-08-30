# Task Domain Model

Phase 1A introduces the canonical task vocabulary and a compatibility persistence bridge. It does **not** replace the current scheduler/request pipeline yet.

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

## Phase 1A shadow-write authority

The current production runtime still **reads** `taskJournal` for resume/reuse decisions. It is therefore still the read authority during this transition.

Runtime task mutations now pass through one adapter and shadow-write both representations with the same `updatedAt`:

```text
runtime mutation
      ↓
Task Journal Adapter
   ↙             ↘
taskJournal     taskRecords
(read authority) (canonical shadow)
```

Canonical shadow semantics currently include:

- normal completed module/source-clean result → `SUCCEEDED + VALID`;
- evidence-supported “暂无分析” module result → `SUCCEEDED + INSUFFICIENT`;
- failed legacy task → canonical `FAILED`;
- retry deletion removes the same task id from both representations.

The two representations must not become independent competing writers. `taskRecords` is now produced by real runtime mutations, but it is not yet used to decide whether work should run.

## Persistence trust boundary

Persisted `taskRecords` are strictly sanitized before they can be restored as the canonical shadow.

A persisted canonical record is accepted only when:

1. its schema, id, task kind, statuses, timestamps, dependency structure and bounded string fields are valid;
2. its id exactly matches the containing record key;
3. its `updatedAt` exactly matches the corresponding sanitized `taskJournal` entry.

If any check fails, the persisted canonical record is discarded and that task safely falls back to a deterministic journal projection.

This means a corrupt, stale or hand-edited canonical shadow cannot override the current production recovery source. It also preserves canonical-only result semantics such as `INSUFFICIENT` when both sides came from the same runtime mutation.

Load-time legacy recovery can still repair or delete journal entries. After those corrections, the renderer reconciles the canonical shadow again, so repaired journal state cannot retain an older mismatched canonical record.

## Storage boundary

`TaskRecord` stores task metadata and references (`outputRef`), not large report/source/model text. The current dual-write bridge does not copy legacy model output into canonical task metadata.

Future storage split remains:

- business/task metadata → repository abstraction
- large artifacts → BlobStore
- observability → JSONL

Phase 1A does not introduce SQLite.

## Next authority switch

The next Task-domain migration step may begin reading canonical task state only after shadow-write behavior has remained stable under real save/recovery tests.

That switch must be explicit and one-directional:

1. canonical TaskRecord becomes the read/write authority;
2. legacy `taskJournal` becomes a compatibility projection for older code/projects;
3. no long-lived dual-authority merge policy is allowed.

Do not remove the legacy journal in the same change that switches authority. First switch read decisions behind a compatibility adapter and keep deterministic fallback for old projects.

## Not implemented in Phase 1A

- canonical TaskRecord read authority
- real Attempt Manager / attempt counting
- Scheduler
- Admission Engine
- Retry Policy
- Failure Classifier
- automatic crash resume
- server request status/cancel/reconcile
- provider cancellation
- billing settlement changes
- SourceUnit/Evidence migration

Those are later phases and must consume this task vocabulary rather than create parallel status systems.
