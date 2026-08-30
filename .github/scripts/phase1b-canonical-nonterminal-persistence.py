from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new)

# 1) Persistence reconcile: keep canonical-only non-success tasks; demote recovered RUNNING to PAUSED.
task_model = Path('product-operation-report-app/src/shared/taskModel.ts')
text = task_model.read_text(encoding='utf-8')
old = """/**
 * During the dual-write bridge the journal remains the read authority. Persisted
 * canonical records are accepted only for journal tasks with the exact same
 * updatedAt, proving both sides came from the same logical mutation.
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
  return projected
}
"""
new = """/**
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
text = replace_once(text, old, new, 'task record reconcile')
task_model.write_text(text, encoding='utf-8')

# 2) Unit tests for canonical-only persistence semantics.
test = Path('product-operation-report-app/src/shared/taskModel.test.ts')
text = test.read_text(encoding='utf-8')
anchor = """  it('projects a sanitized legacy journal into canonical task records without carrying large outputs', () => {
"""
insert = """  it('preserves canonical-only scheduler states and pauses orphaned RUNNING work on recovery', () => {
    const base: TaskRecord = {
      schemaVersion: 1,
      id: 'session:module:v2:product-info',
      kind: 'MODULE_ANALYSIS',
      executionStatus: 'PENDING',
      dependencies: [],
      moduleKey: 'product-info',
      attemptCount: 0,
      createdAt: '2026-08-30T07:00:00.000Z',
      updatedAt: '2026-08-30T07:01:00.000Z',
      migratedFromLegacy: false
    }
    const pending = { ...base }
    const ready = { ...base, id: 'session:module:v2:platform-audience', moduleKey: 'platform-audience' as const, executionStatus: 'READY' as const }
    const waiting = { ...base, id: 'session:module:v2:material-review', moduleKey: 'material-review' as const, executionStatus: 'WAITING_RETRY' as const, retryAt: '2026-08-30T07:10:00.000Z' }
    const running = { ...base, id: 'session:module:v2:voc', moduleKey: 'voc' as const, executionStatus: 'RUNNING' as const, startedAt: '2026-08-30T07:01:00.000Z' }
    const failed = { ...base, id: 'session:module:v2:selling-points', moduleKey: 'selling-points' as const, executionStatus: 'FAILED' as const, errorClass: 'NETWORK' }
    const reconciled = reconcileTaskRecordMirror({}, {
      [pending.id]: pending,
      [ready.id]: ready,
      [waiting.id]: waiting,
      [running.id]: running,
      [failed.id]: failed
    })

    expect(reconciled[pending.id].executionStatus).toBe('PENDING')
    expect(reconciled[ready.id].executionStatus).toBe('READY')
    expect(reconciled[waiting.id]).toMatchObject({ executionStatus: 'WAITING_RETRY', retryAt: waiting.retryAt })
    expect(reconciled[failed.id]).toMatchObject({ executionStatus: 'FAILED', errorClass: 'NETWORK' })
    expect(reconciled[running.id]).toMatchObject({
      executionStatus: 'PAUSED',
      startedAt: running.startedAt,
      migratedFromLegacy: false
    })
  })

  it('rejects canonical-only SUCCEEDED metadata without a matching payload carrier', () => {
    const succeeded = succeededTask({ id: 'session:module:v2:voc', migratedFromLegacy: false })
    expect(reconcileTaskRecordMirror({}, { [succeeded.id]: succeeded })[succeeded.id]).toBeUndefined()
  })

""" + anchor
text = replace_once(text, anchor, insert, 'task model canonical-only tests')
test.write_text(text, encoding='utf-8')

# 3) Windows persistence regression: real save -> disk -> load.
reg = Path('product-operation-report-app/scripts/regression-main.ts')
text = reg.read_text(encoding='utf-8')
anchor = """  const migratedSnapshot: SavedProject = {
"""
insert = """  const schedulerTaskBase = {
    schemaVersion: 1 as const,
    kind: 'MODULE_ANALYSIS' as const,
    dependencies: [],
    attemptCount: 0,
    createdAt: '2026-08-30T07:00:00.000Z',
    updatedAt: '2026-08-30T07:01:00.000Z',
    migratedFromLegacy: false
  }
  const schedulerSnapshot: SavedProject = {
    ...snapshot(7, ''),
    taskRecords: {
      'session:module:v2:product-info': {
        ...schedulerTaskBase,
        id: 'session:module:v2:product-info',
        moduleKey: 'product-info',
        executionStatus: 'PENDING'
      },
      'session:module:v2:material-review': {
        ...schedulerTaskBase,
        id: 'session:module:v2:material-review',
        moduleKey: 'material-review',
        executionStatus: 'WAITING_RETRY',
        retryAt: '2026-08-30T07:10:00.000Z'
      },
      'session:module:v2:voc': {
        ...schedulerTaskBase,
        id: 'session:module:v2:voc',
        moduleKey: 'voc',
        executionStatus: 'RUNNING',
        startedAt: '2026-08-30T07:01:00.000Z'
      }
    }
  }
  await saveLastProject(schedulerSnapshot)
  const restoredScheduler = await loadLastProject()
  assert.equal(restoredScheduler?.taskRecords?.['session:module:v2:product-info']?.executionStatus, 'PENDING', 'canonical-only PENDING survives project persistence')
  assert.equal(restoredScheduler?.taskRecords?.['session:module:v2:material-review']?.executionStatus, 'WAITING_RETRY', 'canonical-only WAITING_RETRY survives project persistence')
  assert.equal(restoredScheduler?.taskRecords?.['session:module:v2:material-review']?.retryAt, '2026-08-30T07:10:00.000Z', 'retryAt survives project persistence')
  assert.equal(restoredScheduler?.taskRecords?.['session:module:v2:voc']?.executionStatus, 'PAUSED', 'orphaned RUNNING is recovered as PAUSED after restart')
  assert.equal(restoredScheduler?.taskRecords?.['session:module:v2:voc']?.startedAt, '2026-08-30T07:01:00.000Z', 'recovered PAUSED task retains its original start timestamp')

""" + anchor
text = replace_once(text, anchor, insert, 'windows scheduler persistence regression')
reg.write_text(text, encoding='utf-8')
