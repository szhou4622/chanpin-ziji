# Product Policy Spec

`src/shared/productPolicy.ts` is the canonical product-facing policy for the active v2 engine.

## Active engine

- Engine: `v2`
- Active module registry: `REPORT_MODULES_V2`
- ProductPolicy must reference the existing registry; do not create a second six-module definition.

## Upload policy

- Maximum top-level uploads: 50
- Maximum total upload size: 350 MB
- Regular file: 40 MB
- Image: 25 MB
- ZIP: 120 MB

Derived pages, sheets, embedded images and ZIP children are not top-level upload count items.

## Source metadata policy

Required:

- attribution
- source kind/category

Optional:

- platform
- note

## Runtime product policy

- local parse concurrency: 2
- AI global concurrency: 4
- vision sub-cap: 2

These are product-side targets. Effective runtime must eventually be `min(client policy, server capability)`.

## Product policy vs safety limits

Do not expose every parser/provider guard as user-configurable product policy. Internal safety guards include ZIP-bomb protection, Office entry limits, PDF page limits, image pixel limits, request-body limits and other resource protection.

Product policy answers “what the product promises”. Safety guards answer “what the runtime must refuse to protect correctness/security”.

## No silent truncation

If a safety limit means business material would be omitted, the system must not silently continue as if analysis were complete. The result must become partial/needs-user-action or fail explicitly.

## Sparse evidence principle

Cardinality is a maximum, not a command to invent content. A validator must never require more items than the available evidence can support.

Resolved in Phase 0:

- M5 VOC still requires all four fixed sections, but each section accepts continuous TOP1-TOPN with N=1..10. Repair instructions explicitly forbid filling to TOP10 without evidence.
- M6 audience × selling point × scene accepts continuous TOP1-TOPN with N=1..5 instead of forcing five combinations.

## Resolved policy drift

The imported v1.1.1 baseline contained several conflicting product rules. Phase 0 aligned them with the canonical policy:

- Production upload copy now distinguishes regular files at 40 MB from ZIP at 120 MB.
- Production source-list copy now states that source kind/category is required; platform and note remain optional.
- `sourceCleanCacheKey()` now hashes the complete accepted `source.note`, so notes that differ after the first 4,000 characters cannot incorrectly share a cache identity. A regression test guards this behavior.

## Package manager

Current release and daily CI use `npm ci`; npm/package-lock is the canonical production path. Unused pnpm lock/workspace files were removed and the package manager is declared in `package.json`. Do not introduce dependency churn during Phase 0.
