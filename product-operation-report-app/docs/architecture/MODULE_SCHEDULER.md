# Module Scheduler Boundary

Phase 1B starts by centralizing the active v2 module dependency graph before introducing a broader Task Scheduler.

## Current responsibility

`moduleDependencyResolver.ts` is the single pure dependency layer for the six report modules.

It currently owns:

- validating unique module ids/keys;
- rejecting missing dependencies and cycles;
- deriving deterministic parallel execution batches from `dependsOn`;
- computing downstream retry/invalidation closure;
- defining whether upstream module execution has settled.

The active v2 graph therefore resolves to:

```text
Batch 1: M1 + M2 + M3 + M5
Batch 2: M4
Batch 3: M6
```

The runtime no longer needs a second hard-coded `[1, 2, 3]` scheduling rule to reproduce this order.

## Dependency semantics

A module dependency is primarily an **ordering dependency**, not a requirement that the upstream result must be successful.

The following upstream module states are terminal for ordering purposes:

- `done`
- `skipped`
- `failed`

This is intentional. The report engine already allows downstream modules to continue with explicit missing-dependency context when evidence or an upstream result is unavailable.

Example:

```text
M1 failed/skipped ─┐
                   ├─ M4 may still run after M1 and M3 have settled
M3 done ───────────┘   and must disclose the missing upstream evidence
```

Treating `failed` or `skipped` as permanently blocking would deadlock partial reports and violate the existing “现有资料分析 / 暂无分析” behavior.

## Retry/invalidation semantics

Retry scope starts from:

1. the explicitly requested module;
2. any module already in `failed` state.

The resolver then adds every transitive downstream dependent.

For the active graph:

- retry M4 → M4 + M6;
- retry M3 → M3 + M4 + M6;
- retry M5(VOC) → M5 + M6.

No module id or downstream chain should be duplicated manually in store code.

## What this is not yet

This resolver is not yet the full Task Scheduler.

It does not own:

- authorization / activation admission;
- points reservation or billing;
- AI/global/vision concurrency slots;
- parse-worker scheduling;
- TaskRecord `PENDING/READY/RUNNING/WAITING_RETRY` transitions;
- transport attempts;
- retry timing/backoff;
- provider routing;
- server request reconciliation.

Those belong to later Phase 1B/1C layers.

## Next safe step

The next scheduler change should consume canonical `TaskRecord` state and this dependency resolver to decide `READY` tasks, while preserving separate executor pools:

```text
Task Scheduler
├─ Local executors
│  ├─ PARSE
│  ├─ NORMALIZE
│  └─ IO
└─ AI executors
   ├─ TEXT
   └─ VISION
```

Do not replace the existing parser utility-process worker pool with the AI scheduler. Dependency/lifecycle control may be unified, but local parse execution and AI execution remain separate resources.
