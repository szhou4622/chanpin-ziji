import { describe, expect, it } from 'vitest'
import type { ProjectTaskSnapshot } from './types'
import {
  dependenciesMatch,
  invalidateTaskResult,
  isReusableTaskResult,
  projectLegacyTaskJournal,
  projectLegacyTaskSnapshot,
  reconcileTaskRecordMirror,
  sanitizeTaskRecords,
  type TaskRecord
} from './taskModel'

function succeededTask(overrides: Partial<TaskRecord> = {}): TaskRecord {
  return {
    schemaVersion: 1,
    id: 'task:m5',
    kind: 'MODULE_ANALYSIS',
    executionStatus: 'SUCCEEDED',
    resultStatus: 'VALID',
    dependencies: [],
    inputFingerprint: 'input:v1',
    resultFingerprint: 'result:v1',
    moduleKey: 'voc',
    attemptCount: 1,
    outputRef: 'blob:result-v1',
    createdAt: '2026-08-30T01:00:00.000Z',
    updatedAt: '2026-08-30T01:01:00.000Z',
    endedAt: '2026-08-30T01:01:00.000Z',
    ...overrides
  }
}

describe('task domain model', () => {
  it('reuses only completed VALID or INSUFFICIENT results with the exact same input identity', () => {
    expect(isReusableTaskResult(succeededTask(), 'input:v1')).toBe(true)
    expect(isReusableTaskResult(succeededTask({ resultStatus: 'INSUFFICIENT' }), 'input:v1')).toBe(true)
    expect(isReusableTaskResult(succeededTask({ resultStatus: 'STALE' }), 'input:v1')).toBe(false)
    expect(isReusableTaskResult(succeededTask({ executionStatus: 'FAILED', resultStatus: undefined }), 'input:v1')).toBe(false)
    expect(isReusableTaskResult(succeededTask(), 'input:v2')).toBe(false)
  })

  it('marks a completed result stale without deleting its output identity', () => {
    const stale = invalidateTaskResult(succeededTask(), '新增用户评价资料', '2026-08-30T02:00:00.000Z', 'source:reviews-v2')
    expect(stale.executionStatus).toBe('SUCCEEDED')
    expect(stale.resultStatus).toBe('STALE')
    expect(stale.outputRef).toBe('blob:result-v1')
    expect(stale.invalidation).toEqual({
      reason: '新增用户评价资料',
      invalidatedBy: 'source:reviews-v2',
      invalidatedAt: '2026-08-30T02:00:00.000Z'
    })
  })

  it('uses dependency result fingerprints rather than timestamps to determine validity', () => {
    const task = succeededTask({
      dependencies: [
        { taskId: 'module:m2', resultFingerprint: 'm2:v1' },
        { taskId: 'module:m4', resultFingerprint: 'm4:v3' },
        { taskId: 'module:m5', resultFingerprint: 'm5:v2' }
      ]
    })
    expect(dependenciesMatch(task, {
      'module:m2': 'm2:v1',
      'module:m4': 'm4:v3',
      'module:m5': 'm5:v2'
    })).toBe(true)
    expect(dependenciesMatch(task, {
      'module:m2': 'm2:v1',
      'module:m4': 'm4:v4',
      'module:m5': 'm5:v2'
    })).toBe(false)
  })

  it('strictly sanitizes persisted canonical records and drops malformed state', () => {
    const valid = succeededTask({
      id: 'session:module:v2:voc@run-a',
      logicalKey: 'session:module:v2:voc',
      payloadKey: 'session:module:v2:voc',
      resultStatus: 'INSUFFICIENT',
      updatedAt: '2026-08-30T03:00:00.000Z',
      createdAt: '2026-08-30T02:59:00.000Z',
      migratedFromLegacy: false
    })
    const sanitized = sanitizeTaskRecords({
      [valid.id]: valid,
      'bad:id-mismatch': { ...valid, id: 'another-id' },
      'bad:failed-with-result': { ...valid, id: 'bad:failed-with-result', executionStatus: 'FAILED', resultStatus: 'VALID' },
      'bad:date': { ...valid, id: 'bad:date', updatedAt: 'not-a-date' },
      'bad:module': { ...valid, id: 'bad:module', moduleKey: 'made-up-module' },
      'bad:logical': { ...valid, id: 'bad:logical', logicalKey: 'bad logical key' },
      'bad:payload': { ...valid, id: 'bad:payload', payloadKey: 'bad payload key' }
    })

    expect(sanitized).toEqual({ [valid.id]: valid })
  })

  it('accepts a canonical mirror only when it matches the same journal mutation', () => {
    const journal: Record<string, ProjectTaskSnapshot> = {
      'session:module:v2:voc': {
        kind: 'module',
        status: 'complete',
        output: '暂无分析：证据不足',
        inputFingerprint: 'voc-input',
        updatedAt: '2026-08-30T03:00:00.000Z'
      }
    }
    const canonical = succeededTask({
      id: 'session:module:v2:voc',
      resultStatus: 'INSUFFICIENT',
      inputFingerprint: 'voc-input',
      updatedAt: '2026-08-30T03:00:00.000Z',
      createdAt: '2026-08-30T02:59:00.000Z',
      migratedFromLegacy: false
    })
    expect(reconcileTaskRecordMirror(journal, { [canonical.id]: canonical })[canonical.id].resultStatus).toBe('INSUFFICIENT')

    const staleCanonical = { ...canonical, updatedAt: '2026-08-30T02:59:59.000Z' }
    const fallback = reconcileTaskRecordMirror(journal, { [canonical.id]: staleCanonical })[canonical.id]
    expect(fallback.resultStatus).toBe('VALID')
    expect(fallback.migratedFromLegacy).toBe(true)
  })

  it('preserves canonical-only scheduler states and pauses orphaned RUNNING work on recovery', () => {
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

  it('projects a sanitized legacy journal into canonical task records without carrying large outputs', () => {
    const journal: Record<string, ProjectTaskSnapshot> = {
      'clean:source-a': {
        kind: 'source_clean',
        status: 'complete',
        output: '大段旧清洗结果不应复制进TaskRecord',
        inputFingerprint: 'clean-input',
        updatedAt: '2026-08-20T02:00:00.000Z'
      },
      'module:m5': {
        kind: 'module',
        status: 'interrupted',
        updatedAt: '2026-08-20T02:01:00.000Z'
      }
    }
    const projected = projectLegacyTaskJournal(journal)
    expect(projected['clean:source-a']).toMatchObject({
      kind: 'SOURCE_CLEAN',
      executionStatus: 'SUCCEEDED',
      resultStatus: 'VALID',
      inputFingerprint: 'clean-input',
      migratedFromLegacy: true
    })
    expect(projected['module:m5'].executionStatus).toBe('PAUSED')
    expect('legacyOutput' in projected['clean:source-a']).toBe(false)
  })

  it('projects legacy task journal records deterministically without rewriting inline output', () => {
    const complete: ProjectTaskSnapshot = {
      kind: 'module',
      status: 'complete',
      output: '旧模块结果',
      inputFingerprint: 'legacy-input',
      updatedAt: '2026-08-20T03:00:00.000Z'
    }
    const projected = projectLegacyTaskSnapshot('legacy:module:5', complete)
    expect(projected.task).toMatchObject({
      id: 'legacy:module:5',
      logicalKey: 'legacy:module:5',
      payloadKey: 'legacy:module:5',
      kind: 'MODULE_ANALYSIS',
      executionStatus: 'SUCCEEDED',
      resultStatus: 'VALID',
      inputFingerprint: 'legacy-input',
      attemptCount: 0,
      migratedFromLegacy: true
    })
    expect(projected.legacyOutput).toBe('旧模块结果')

    const interrupted = projectLegacyTaskSnapshot('legacy:clean:1', {
      kind: 'source_clean',
      status: 'interrupted',
      updatedAt: '2026-08-20T03:01:00.000Z'
    })
    expect(interrupted.task.executionStatus).toBe('PAUSED')
    expect(interrupted.task.resultStatus).toBeUndefined()
  })
})
