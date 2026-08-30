# Active V2 Path

> Current production architecture baseline for the v2 six-module engine.

## Active report engine

`REPORT_MODULES === REPORT_MODULES_V2`.

Active modules are exactly:

1. M1 产品信息 (`product-info`)
2. M2 成交人群分析 (`platform-audience`)
3. M3 内容素材判断 (`material-review`)
4. M4 卖点提炼与排序 (`selling-points`)
5. M5 用户真实需求VOC (`voc`)
6. M6 人群×卖点×场景匹配 (`audience-sp-scene`)

Active DAG:

```text
Wave 1: M1 / M2 / M3 / M5
M4 <- M1 + M3
M6 <- M2 + M4 + M5
```

No active v2 module requires web search.

## Production happy path

```text
Renderer UI
  -> store.startGeneration
  -> source parse / normalize / clean
  -> source confirmation
  -> v2 module analysis
  -> assembleModuleReport
  -> report preview
  -> Markdown / HTML / Word presentation/export
```

The v2 report is deterministically assembled from module outputs. Phase 0 must not add another final-model synthesis call.

## Source processing

Local parsing is isolated in utility processes. Structured tables may be handled locally; semantic tables/documents/images may create model cleaning jobs. Parser safety guards, BlobStore, source cache and no-silent-truncation behavior are active infrastructure and are not part of the legacy report engine.

## Persistence

Current project persistence uses:

- revision protection
- primary + backup manifests
- content-addressed BlobStore
- partial restore when a blob is missing
- task journal checkpoints

Phase 0 does not replace this with SQLite.

## AI request path

```text
Renderer
 -> preload IPC
 -> Main chat admission / request registry
 -> managed proxy client
 -> server /chat/completions
 -> provider route
```

The current request lifecycle has known reconciliation/cancel limitations documented in `REQUEST_PROTOCOL.md`.

## Report presentation

Internal module/report text may contain evidence identifiers. User-facing Markdown/HTML/Word presentation converts internal provenance into readable source names where supported. Presentation is not the source of truth for evidence.

## Explicitly not active v2

The following are not part of the active six-module production analysis path:

- `REPORT_MODULES_V1`
- `benchmark-brands`
- `selling-point-ranking`
- old 0-11 final-report synthesis engine
- `FINAL_REPORT_PARTS`
- legacy SOP step dependency semantics

They may remain reachable for migration, legacy rendering or tests. See `LEGACY_MAP.md`.
