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

Legacy attempt count is unknown, so the compatibility projection uses `attemptCount = 0` as an explicit migration sentinel; native Task Engine records will count real attempts.

## Phase 1A persistence bridge authority

During the compatibility bridge, the current production runtime still writes `taskJournal`.

On save/load, the sanitized journal is projected deterministically into `taskRecords` and both are persisted. The projected `taskRecords` are therefore a **read-only compatibility mirror**, not yet an independent source of truth.

This is intentional:

- old projects remain recoverable without model work;
- current runtime behavior does not change;
- large legacy output text is not duplicated into `TaskRecord`;
- corrupt or arbitrary persisted `taskRecords` are not trusted as authoritative state during this bridge.

When native TaskRecord writers are introduced, authority must switch explicitly in one migration step: canonical records must receive strict sanitization and become the write source of truth. Do not leave `taskJournal` and native `taskRecords` as long-lived competing writers, and do not silently overwrite native records with a legacy projection.

## Storage boundary

`TaskRecord` stores task metadata and references (`outputRef`), not large report/source/model text.

Future storage split remains:

- business/task metadata → repository abstraction
- large artifacts → BlobStore
- observability → JSONL

Phase 1A does not introduce SQLite.

## Not implemented in Phase 1A

- native TaskRecord writer authority
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
