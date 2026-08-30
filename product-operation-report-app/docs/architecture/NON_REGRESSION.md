# Non-regression Contract

The following existing capabilities must survive architectural refactors unless an explicit product decision replaces them.

## Project and persistence

1. Project revision prevents late/older snapshots from overwriting newer state.
2. Primary + backup recovery remains available.
3. Large project content remains externalized in content-addressed blobs.
4. One missing blob must not erase the entire project.
5. Disk preflight remains before large persistence operations.
6. Orphan blobs remain safely prunable.
7. Completed source-clean/module work may be reused when its exact input remains valid.

## Parsing and completeness

8. Local parsing remains isolated from renderer UI execution.
9. Parser worker failure must not silently corrupt unrelated files.
10. ZIP bomb and resource safety guards remain active.
11. Safety-limit omission must never be silent.
12. Key Office/PDF visual content that cannot be read must surface a warning/error rather than pretending completeness.
13. Structured table parsing must preserve real populated cells instead of expanding huge formatted empty ranges.

## Evidence and report

14. Internal evidence identifiers remain traceable to original material.
15. User-facing report presentation may show readable source names instead of internal evidence ids.
16. Markdown/HTML/Word remain renders of the same report content rather than independent reports.
17. File export remains atomic/temp-then-rename where implemented.
18. Sparse evidence must not be expanded by validators merely to fill TOP-N slots.

## AI execution

19. Cross-model fallback must not concatenate visible partial output from different models.
20. Cancel/abort is not success.
21. Missing source categories do not globally block all other valid modules.
22. Module DAG invalidation propagates only to affected downstream branches.
23. The active v2 engine remains exactly M1-M6 unless a deliberate product change updates contract + tests.

## Migration

24. V1 -> V2 project migration remains deterministic.
25. Migration must not silently trigger paid AI/model work.
26. Old benchmark content may remain as a clearly labeled legacy appendix.

## Security / commercial infrastructure

27. Electron sandbox/context isolation/no-node-integration security posture must not regress.
28. Packaged production must not expose provider API secrets to renderer/user storage.
29. safeStorage-protected device/license data remains protected.
30. Device unbind must not accidentally rotate the stable device identity.
31. Rebinding to a new machine must not grant initial benefits twice.
32. Offline grace must not erase access to already-local historical reports.
33. Update manifest signature and SHA verification remain enforced.
34. Update downloads remain restricted to approved official endpoints/formats.
35. ProviderKeyring last-known-good configuration behavior remains intact.
36. Server wallet/ledger transactional behavior and platform daily cost fuse remain intact.
37. TokenUsage and cost-optimization observability remain available without storing business content.

## Architecture rule

Tests must protect current product contracts, not obsolete implementation accidents. If a test conflicts with an approved product contract, classify/update the test rather than reverting correct product behavior simply to keep an outdated assertion green.
