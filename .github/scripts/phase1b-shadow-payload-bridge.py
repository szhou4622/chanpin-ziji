from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new)

model = Path('product-operation-report-app/src/shared/taskModel.ts')
text = model.read_text(encoding='utf-8')

old = """/**
 * Reconciles legacy payload-backed tasks with canonical task metadata.
 *
 * - A journal-backed task accepts canonical metadata only when both sides share the
 *   same id + updatedAt mutation.
 * - A canonical-only task may survive persistence while it has not succeeded yet;
 *   scheduler states do not have a legacy journal representation.
 * - A persisted RUNNING task is recovered as PAUSED because the process that owned
 *   the execution no longer exists after application restart.
 * - A canonical-only SUCCEEDED task is rejected here: completed output must remain
 *   tied to a verified payload/output migration rather than metadata alone.
 */
export function reconcileTaskRecordMirror(
  journal: Readonly<Record<string, ProjectTaskSnapshot>>,
  persisted: Readonly<Record<string, TaskRecord>>
): Record<string, TaskRecord> {
  const projected = projectLegacyTaskJournal(journal)
  for (const [taskId, snapshot] of Object.entries(journal)) {
    const canonical = persisted[taskId]
    if (canonical && canonical.id === taskId && canonical.updatedAt === snapshot.updatedAt) {
      projected[taskId] = canonical
    }
  }
  for (const [taskId, canonical] of Object.entries(persisted)) {
    if (journal[taskId] || canonical.id !== taskId || canonical.executionStatus === 'SUCCEEDED') continue
    projected[taskId] = canonical.executionStatus === 'RUNNING'
      ? {
          ...canonical,
          executionStatus: 'PAUSED',
          resultStatus: undefined,
          retryAt: undefined,
          endedAt: undefined
        }
      : canonical
  }
  return projected
}
"""

new = """function completedTaskHasVerifiedPayload(
  canonical: TaskRecord,
  journal: Readonly<Record<string, ProjectTaskSnapshot>>
): boolean {
  if (canonical.executionStatus !== 'SUCCEEDED' || !canonical.payloadKey) return false
  const payload = journal[canonical.payloadKey]
  if (!payload || payload.status !== 'complete') return false
  if (LEGACY_KIND_MAP[payload.kind] !== canonical.kind) return false
  if (payload.updatedAt !== canonical.updatedAt) return false
  if (canonical.inputFingerprint && payload.inputFingerprint !== canonical.inputFingerprint) return false
  return true
}

/**
 * Reconciles legacy payload-backed tasks with canonical task metadata.
 *
 * - A journal-backed task accepts canonical metadata only when both sides share the
 *   same id + updatedAt mutation.
 * - A canonical-only task may survive persistence while it has not succeeded yet;
 *   scheduler states do not have a legacy journal representation.
 * - A persisted RUNNING task is recovered as PAUSED because the process that owned
 *   the execution no longer exists after application restart.
 * - A completed immutable Task instance may survive only when payloadKey points to
 *   a complete legacy payload with the same kind, input fingerprint and updatedAt.
 *   This keeps the compatibility bridge fail-closed: metadata alone cannot prove a
 *   completed business result exists.
 */
export function reconcileTaskRecordMirror(
  journal: Readonly<Record<string, ProjectTaskSnapshot>>,
  persisted: Readonly<Record<string, TaskRecord>>
): Record<string, TaskRecord> {
  const projected = projectLegacyTaskJournal(journal)
  for (const [taskId, snapshot] of Object.entries(journal)) {
    const canonical = persisted[taskId]
    if (canonical && canonical.id === taskId && canonical.updatedAt === snapshot.updatedAt) {
      projected[taskId] = canonical
    }
  }
  for (const [taskId, canonical] of Object.entries(persisted)) {
    if (journal[taskId] || canonical.id !== taskId) continue
    if (canonical.executionStatus === 'SUCCEEDED') {
      if (completedTaskHasVerifiedPayload(canonical, journal)) projected[taskId] = canonical
      continue
    }
    projected[taskId] = canonical.executionStatus === 'RUNNING'
      ? {
          ...canonical,
          executionStatus: 'PAUSED',
          resultStatus: undefined,
          retryAt: undefined,
          endedAt: undefined
        }
      : canonical
  }
  return projected
}
"""

text = replace_once(text, old, new, 'reconcile payload-backed completed task')
model.write_text(text, encoding='utf-8')
