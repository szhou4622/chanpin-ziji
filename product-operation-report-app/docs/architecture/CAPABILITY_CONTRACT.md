# Capability Contract

Phase 0 defines authority boundaries only. Runtime capability discovery is a later phase.

## Control plane

Short JSON requests:

- activation/session
- wallet
- health
- future capabilities
- future request status
- future cancel

## Data plane

Long-running model traffic:

- `/chat/completions`
- SSE streaming
- large request bodies
- model/provider attempts
- verified token usage

## Authority

- ProductPolicy: client product promise/target behavior.
- Server Capability: effective non-secret server runtime limits.
- Provider Capability: model/route-specific limits and availability.

Future effective limits should be computed from all applicable layers rather than duplicated literals.

## Current known server behavior

Current proxy behavior includes a hidden concurrency rule equivalent to:

```text
one license
 -> one active report_session at a time
 -> max 4 concurrent model requests inside that report
```

Document this as a current capability; do not change it in Phase 0.

## Capability categories

A future non-secret capabilities endpoint may expose:

- protocol version
- request/body/image limits
- active-report and request concurrency
- enabled model identifiers
- effective safe output limits
- heartbeat interval/semantics
- timeout policy categories

It must never expose provider secrets, API keys or sensitive route credentials.

## Timeout semantics

Transport activity is not meaningful model output. Keepalive heartbeats must not reset future meaningful-content timeout accounting.

Track separately when implemented:

- transport first byte
- first meaningful model content
- last transport activity
- last meaningful model content
- absolute deadline

## Provider routing

Preserve the existing ProviderKeyring/last-known-good behavior. Prefer same-model route/key recovery before cross-model fallback. Never join partial visible output from different models into one result.
