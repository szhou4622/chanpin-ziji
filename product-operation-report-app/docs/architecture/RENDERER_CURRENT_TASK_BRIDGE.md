# Renderer Current Task Bridge

This bridge makes `currentTaskByLogicalKey` part of renderer project state without giving it execution authority yet.

## Scope

The renderer now carries three related structures:

```text
taskJournal             legacy payload/output carrier
taskRecords             canonical task metadata
currentTaskByLogicalKey explicit pointer from logical slot to current Task instance
```

The current-task index is persisted, restored, reset with a new analysis, and preserved during reset rollback.

It is **not** used by the production execution path yet.

## Restore order

The renderer must not trust a previously sanitized pointer blindly because renderer-side compatibility repair may still modify or remove legacy journal entries after the main process loads the project.

Restore therefore follows this order:

```text
load SavedProject
    ↓
renderer compatibility repair of taskJournal/module outputs
    ↓
reconcileTaskRecordMirror(...)
    ↓
sanitizeTaskCurrentIndex(..., reconciledTaskRecords)
    ↓
store currentTaskByLogicalKey
```

A pointer to a Task removed by renderer recovery is dropped rather than redirected to another Task by timestamp or string ordering.

## New-analysis rule

Any operation that invalidates the active analysis state clears all three task structures together:

```text
taskJournal = {}
taskRecords = {}
currentTaskByLogicalKey = {}
```

This prevents a current pointer from surviving after its Task records have been discarded.

## Persistence rule

`buildProjectSnapshot()` writes `currentTaskByLogicalKey` explicitly. If an older renderer state has no field, it serializes an empty index.

No current Task is inferred during snapshot creation.

## Explicitly not implemented here

- no Scheduler ownership
- no shadow lifecycle
- no new Task instance creation in the runtime
- no runtime current-task lookup for module execution
- no changes to `taskJournal` keys
- no changes to model `taskKey`
- no changes to `billingRequestId`
- no server request status/cancel/reconcile
- no 409 lifecycle fix
- no billing behavior change

The next safe step is shadow lifecycle observation: existing production execution remains authoritative while canonical Task instances record the same execution transitions beside it.
