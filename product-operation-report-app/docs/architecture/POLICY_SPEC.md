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

Known current conflicts to fix after Phase 0:

- M5 VOC prompt allows fewer than TOP10, but current validator/tests can force TOP10.
- M6 prompt allows fewer than TOP5, but current validator can force TOP5.

## Package manager

Current release CI uses `npm ci`; npm/package-lock is the current canonical production path. Do not introduce dependency churn during Phase 0.
