import { describe, expect, it } from 'vitest'
import type { ProjectTaskSnapshot } from './types'
import {
  dependenciesMatch,
  invalidateTaskResult,
  isReusableTaskResult,
  projectLegacyTaskJournal,
  projectLegacyTaskSnapshot,
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
