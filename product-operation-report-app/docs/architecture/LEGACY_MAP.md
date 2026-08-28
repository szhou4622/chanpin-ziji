# Legacy Map

This file separates production v2 behavior from compatibility and dormant code. Do not delete legacy code only because it is not on the active happy path.

| Area | Classification | Purpose / deletion condition |
| --- | --- | --- |
| `REPORT_MODULES_V1` | LEGACY_COMPAT | Deterministic old-project migration and legacy rendering. Remove only after old projects no longer need migration. |
| `SOP_STEPS` / `LEGACY_SOP_STEPS` | LEGACY_COMPAT | Pre-module report rendering / old project semantics. Active v2 code must not depend on it except allowlisted compatibility code. |
| `benchmark-brands` module/prompt | LEGACY_COMPAT | Old M4 benchmark and legacy appendix. Not active v2. |
| `selling-point-ranking` module/prompt | LEGACY_COMPAT | Old M7 ranking. New M4 already fuses selling point extraction/ranking. |
| old 0-11 final report engine | LEGACY_COMPAT | Legacy report generation/revision. Current v2 uses deterministic six-module assembly. |
| `FINAL_REPORT_PARTS` / partial final rerun helpers | LEGACY_COMPAT / TEST_ONLY | Old report-part revision behavior and regression coverage. |
| Search infrastructure | LEGACY_DORMANT | V2 modules currently all use `needsWebSearch=false`; retain for possible future research capability and old benchmark compatibility. |
| User-managed provider profiles | DEVELOPMENT_ONLY | Packaged production uses managed proxy and strips user provider credentials. |
| `purpose` source field | LEGACY_COMPAT | Free-text legacy classification retained for old project/cache compatibility; current category is `kindV1` / future `SourceCategory`. |
| numeric report artifact step id (for example report step 9) | LEGACY_COMPAT | Persistence coupling from old SOP. Replace later with semantic artifact ids; do not migrate persistence in Phase 0. |
| old server task types (`summary`, `analysis_step`, `final_part`, `revision_part`, `module_benchmark`, `module_ranking`) | LEGACY_COMPAT | Server still accepts historical task types. Active v2 must not accidentally route benchmark/ranking tasks. |

## Production reachability rule

A search hit is not proof that code is active. Every future audit must distinguish:

1. Production reachability
2. Migration reachability
3. Test reachability

Only code proven unreachable from all three may be classified `DEAD_CODE`.

## Active v2 forbidden dependencies

New active v2 production code must not introduce dependencies on:

- `REPORT_MODULES_V1`
- `benchmark-brands`
- `selling-point-ranking`
- old final report part generation
- old SOP step numbering

unless the call site is explicitly migration/legacy rendering compatibility code.
