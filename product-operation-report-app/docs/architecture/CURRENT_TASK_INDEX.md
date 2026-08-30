# Current Task Index

A stable business slot may have multiple immutable Task instances over time. The runtime must therefore store an explicit pointer to the current instance instead of guessing from timestamps, string prefixes or array order.

## Contract

The persisted index is:

```text
currentTaskByLogicalKey[logicalKey] = TaskRecord.id
```

Example:

```text
slot: M5 VOC
logicalKey = report:123:module:v2:voc

history:
  report:123:module:v2:voc@run-a  SUCCEEDED + STALE
  report:123:module:v2:voc@run-b  SUCCEEDED + VALID

currentTaskByLogicalKey:
  report:123:module:v2:voc -> report:123:module:v2:voc@run-b
```

The index, not `updatedAt`, decides which Task is current.

## Why timestamps are forbidden as selection identity

Timestamps are useful observability metadata, but they are not a safe identity mechanism:

- clock values may collide;
- persisted state can be restored from backups;
- stale and current tasks may have later metadata updates for unrelated reasons;
- invalidation changes `updatedAt` on historical completed tasks;
- retry/recovery can reorder writes.

Therefore no scheduler/repository code should scan all records and pick the most recently updated Task for a logical slot.

## Registration rule

`registerCurrentTask()` atomically returns a new TaskRecord map and current index.

A new Task instance may become current only when:

1. no current instance exists; or
2. the previous current instance is `SUCCEEDED`; or
3. the previous current instance is `CANCELLED`.

A current task in any retryable/live state cannot be silently replaced:

- `PENDING`
- `READY`
- `RUNNING`
- `WAITING_RETRY`
- `PAUSED`
- `FAILED`

This prevents two logical tasks for the same business slot from being considered current at the same time.

`FAILED` is intentionally not replaceable because the Task lifecycle allows `FAILED → READY`. If the product decides to abandon that failed Task and create a replacement, the old Task should first be explicitly cancelled/retired by the owning workflow rather than silently losing its current pointer.

## Idempotency and ID collision

Registering the same persisted Task instance again is idempotent. Object reference equality is not used because restored JSON creates new JavaScript objects.

If a record already exists under the same Task id, its immutable creation identity must match:

- id
- logicalKey
- payloadKey
- task kind
- input fingerprint
- source/module identity
- createdAt

A mismatch is treated as an ID collision and fails closed. Existing durable state is never overwritten by a new object merely because the id string matches.

## Safe pointer clear

Pointer deletion is compare-and-clear:

```text
clearCurrentTask(logicalKey, expectedTaskId)
```

The pointer is removed only if it still points to the task id observed by the caller. This prevents a delayed cleanup action for Task A from accidentally deleting a newer Task B pointer.

## Persistence recovery

`SavedProject` carries optional `currentTaskByLogicalKey`.

Restore order is important:

```text
raw project
  ↓
sanitize taskJournal
  ↓
sanitize TaskRecords
  ↓
reconcile legacy/canonical TaskRecords
  ↓
sanitize currentTaskByLogicalKey against the recovered TaskRecords
```

A persisted pointer is dropped when:

- its logical key is malformed;
- its Task id is malformed;
- the Task record no longer exists after sanitation/recovery;
- the pointed Task belongs to another logicalKey.

The sanitizer never invents a replacement pointer based on recency.

## Legacy compatibility

Older projects do not contain `currentTaskByLogicalKey`. They restore with an empty current index.

This phase does not automatically infer current pointers for legacy records. Any later bootstrap/migration must be explicit and deterministic.

Current production runtime remains unchanged and can continue using the legacy journal/read bridge until the shadow lifecycle integration is ready.

## Current boundary

This phase does **not** yet:

- add current index state to the renderer store;
- switch module reads to the current index;
- create replacement Task instances during real analysis;
- change taskJournal keys or payload lookup;
- change model taskKey/billingRequestId;
- change server request identity;
- start Scheduler execution ownership.

The index is currently a tested shared-domain and persistence capability.

## Next safe step

The next integration can finally shadow the existing module executor without reopening terminal Tasks:

1. for work that can reuse an existing valid result, keep the existing completed Task current;
2. for genuinely new module work, create a new Task instance under the module logicalKey;
3. register that instance in `currentTaskByLogicalKey`;
4. drive `PENDING → READY → RUNNING` through the lifecycle reducer immediately around the **existing** executor;
5. map the existing real outcome to `SUCCEEDED / FAILED / PAUSED`;
6. keep the current three-batch executor, AI concurrency and model request behavior unchanged;
7. observe and regression-test the shadow state before giving Scheduler ownership of execution.
