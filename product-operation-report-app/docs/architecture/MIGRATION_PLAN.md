# Migration Plan

This repository is being refactored in small phases. Phase boundaries exist to prevent one bug fix from silently rewriting unrelated subsystems.

## Phase 0 — architecture closure

- confirm active production path
- classify active/legacy/test-only code
- establish ProductPolicy
- add architecture guard tests
- add daily CI
- document request/capability/non-regression contracts
- correct safe current-copy/rule drift only

Do not implement the future task engine, client SQLite, adaptive planner or server request lifecycle here.

## Phase 1A — domain task model

Introduce/evolve the existing task journal into a formal model for:

- Job
- Attempt
- execution status
- result status
- dependencies
- atomic claim
- input/result fingerprints
- persistence/recovery

Use the existing repository/blob persistence first. SQLite is only a candidate after this complexity is understood.

## Phase 1B — scheduler + admission

Unify business scheduling while preserving separate executors/resources:

- parse pool
- AI pool
- vision sub-cap
- dependency resolver
- admission engine
- current request registry

Task state is unified; all work must not share one physical thread pool.

## Phase 1C — failure + retry

Create structured failure classification and retry policy instead of multiple string-regex policies. Differentiate retryable transport/provider errors, user-action failures, balance pauses, cancellation and validation warnings.

## Phase 2 — server request lifecycle

Add request status/cancel/reconcile protocol and remove the 409 overlap race. User stop must cancel server/provider attempts where possible. Final billing must settle only verified provider usage; estimates are for planning/reservation, not final user charge.

## Phase 3 — structured data/evidence

Evolve toward:

```text
Raw Source
 -> Parsed Source
 -> Source Unit
 -> Normalized Unit
 -> Evidence
 -> Base Insight
 -> Source Aggregate
 -> Category Aggregate
 -> Analysis View
 -> Module Structured Result
 -> Report
```

Use full-content cryptographic fingerprints and program-owned provenance. Do not rely on Markdown strings as the primary database.

## Phase 4 — adaptive planner

Replace fixed reliability heuristics such as 28K text batches / fixed image grouping with route/model-aware safe envelopes. Existing hard safety limits remain separate from adaptive targets.

## Phase 5 — instruction and validity protocol

Version analysis/module instructions and persist canonical dependency snapshots. Artifact validity must be determined by input/dependency fingerprints rather than timestamps alone.

## Phase 6 — report review/versioning

Restore explicit report review/second confirmation, add report versions and final/draft semantics, and make presentation consume structured results.

## Known early fixes after Phase 0

- M5 validator/test currently forces TOP10 despite prompt allowing fewer results.
- M6 validator currently forces TOP5 despite prompt allowing fewer results.
- retry-one-module currently can include unrelated failed branches.
- multi-sheet semantic routing can be biased by the first sheet.
- saved-project recovery does not fully invalidate results when current prompt/runtime bundle changes.
- old report persistence remains coupled to numeric SOP artifact ids.
- complete report cache restores content without full execution lineage.

## Migration invariants

- Existing V1 -> V2 migration stays deterministic.
- Migration/schema upgrades must not silently create paid model requests.
- Old projects remain readable until an explicit deprecation policy says otherwise.
- No native dependency is introduced in Phase 0.
