# Task Identity Boundary

The canonical Task lifecycle makes `SUCCEEDED` and `CANCELLED` terminal. Therefore one durable Task id cannot also be the permanent business-slot id for work that may be recomputed after inputs change.

## Three identities

The task domain separates three concepts:

```text
logicalKey
  = stable business slot
  = "which piece of business work is this?"

TaskRecord.id
  = immutable logical-task instance
  = "which concrete execution lifecycle is this?"

payloadKey
  = transitional legacy payload location
  = "where is the old inline journal output stored?"
```

Example for report module M5:

```text
logicalKey = report-session:module:v2:voc

first task instance
id = report-session:module:v2:voc@run-a

inputs change / explicit recompute
second task instance
id = report-session:module:v2:voc@run-b

legacy payload during migration
payloadKey = report-session:module:v2:voc
```

The first task may remain `SUCCEEDED + STALE` while the second task progresses through `PENDING → READY → RUNNING`.

A completed Task is never reopened merely because the same business slot needs a new result.

## Compatibility rule

Existing projects predate this identity split. They remain valid without migration work:

```text
id = logicalKey = payloadKey = legacy task id
```

`logicalKey` and `payloadKey` are optional in persisted schema v1 records. When `logicalKey` is absent, domain helpers resolve it to `id`.

Legacy journal projection explicitly assigns both `logicalKey` and `payloadKey` to the old task id. No model call, content rewrite or report recomputation is involved.

## Identity validation

All three persisted keys use the same bounded safe identity character set.

New task instance ids are built from:

```text
<logicalKey>@<instanceToken>
```

The instance token is generated once by the caller and then persisted. It is not regenerated during restore.

Malformed, oversized or hand-edited identity fields are rejected by the project task sanitizer rather than becoming authoritative runtime state.

## Current runtime boundary

This phase introduces vocabulary and persistence only.

The active production runtime still uses the legacy stable module key for its current journal/read bridge. In particular, this change does **not** yet modify:

- `taskJournal` keys;
- `readRuntimeTaskState()` lookup behavior;
- module execution in `store.ts`;
- model `taskKey` headers;
- `billingRequestId`;
- server request identity;
- report cache identity.

That is intentional. Unique Task instance ids must not be switched on until current-task selection and legacy payload mapping exist as explicit runtime boundaries.

## Current-task selection target

The later scheduler must maintain the distinction between history and current work:

```text
logicalKey
   ├─ old Task A: SUCCEEDED + STALE
   └─ current Task B: PENDING / READY / RUNNING / ...
```

A selector/repository boundary should resolve the current Task instance for a `logicalKey`; consumers must not guess by timestamp or by string prefix.

Replacement is explicit:

1. retain the previous terminal Task instance;
2. create a new Task id under the same `logicalKey`;
3. bind the new Task to the current input/dependency fingerprints;
4. make that new instance current;
5. never transition the old `SUCCEEDED` record back to `READY`.

## Payload migration target

`payloadKey` exists only because completed output is still carried by the legacy journal in part of the runtime.

During the transition:

```text
Task instance metadata
        ↓ payloadKey
legacy journal payload
```

Long term, a trusted Artifact/Blob `outputRef` replaces this indirection and `payloadKey` can be retired.

Until then, a canonical-only `SUCCEEDED` record is still not sufficient proof of a completed usable output.

## Relationship to Attempt identity

Task identity and Attempt identity are different layers:

```text
logicalKey
   ↓
TaskRecord.id       one immutable business-task instance
   ↓
AttemptRecord.id    one execution/provider attempt
   ↓
requestId           one transport request
```

Automatic transport retries must not create a new logical Task merely because a request failed. Conversely, changing business inputs must create a new Task instance rather than pretending it is another transport attempt of the old completed Task.

## Relationship to billing identity

This phase does not change billing ids.

Future request/billing work must explicitly decide which identifier is used for:

- logical billable work;
- provider attempt;
- transport request;
- idempotent settlement.

Do not reuse `logicalKey`, `TaskRecord.id`, `AttemptRecord.id`, `requestId` and `billingLogicalId` interchangeably.

## Next safe step

Before shadow lifecycle is wired into the real module executor, add a pure current-task selection/replacement layer that can:

1. list task instances by `logicalKey`;
2. identify the current instance deterministically;
3. create a replacement instance without reopening a terminal Task;
4. retain old completed/stale history;
5. preserve compatibility with legacy records where `id = logicalKey = payloadKey`.

Only after that layer is tested should the existing three-batch executor shadow-write `PENDING → READY → RUNNING → terminal` states.
