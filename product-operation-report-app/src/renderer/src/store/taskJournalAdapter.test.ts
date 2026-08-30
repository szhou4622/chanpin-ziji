import { describe, expect, it } from 'vitest'
import type { ProjectTaskSnapshot } from '../../../shared/types'
import type { TaskRecord } from '../../../shared/taskModel'
import {
  removeRuntimeTaskState,
  removeTaskJournalEntries,
  writeRuntimeTaskState,
  writeTaskJournalEntry
} from './taskJournalAdapter'

describe('task journal compatibility adapter', () => {
  it('writes immutably and injects one canonical timestamp', () => {
    const original: Record<string, ProjectTaskSnapshot> = {
      old: { kind: 'module', status: 'complete', updatedAt: '2026-08-20T00:00:00.000Z' }
    }
    const next = writeTaskJournalEntry(
      original,
      'module:m5',
      { kind: 'module', status: 'failed', output: 'partial', inputFingerprint: 'fp-1' },
      () => '2026-08-30T06:30:00.000Z'
    )

    expect(next).not.toBe(original)
    expect(original['module:m5']).toBeUndefined()
    expect(next['module:m5']).toEqual({
      kind: 'module',
      status: 'failed',
      output: 'partial',
      inputFingerprint: 'fp-1',
      updatedAt: '2026-08-30T06:30:00.000Z'
    })
    expect(next.old).toBe(original.old)
  })

  it('dual-writes one timestamp and preserves supported canonical metadata', () => {
    const next = writeRuntimeTaskState(
      {},
      {},
      'session:module:v2:voc',
      {
        kind: 'module',
        status: 'complete',
        output: '暂无分析：证据不足',
        inputFingerprint: 'voc-input-v2',
        resultStatus: 'INSUFFICIENT',
        moduleKey: 'voc'
      },
      () => '2026-08-30T06:31:00.000Z'
    )

    expect(next.taskJournal['session:module:v2:voc'].updatedAt).toBe('2026-08-30T06:31:00.000Z')
    expect(next.taskRecords['session:module:v2:voc']).toMatchObject({
      schemaVersion: 1,
      id: 'session:module:v2:voc',
      kind: 'MODULE_ANALYSIS',
      executionStatus: 'SUCCEEDED',
      resultStatus: 'INSUFFICIENT',
      moduleKey: 'voc',
      inputFingerprint: 'voc-input-v2',
      createdAt: '2026-08-30T06:31:00.000Z',
      updatedAt: '2026-08-30T06:31:00.000Z',
      migratedFromLegacy: false
    })
  })

  it('keeps canonical createdAt across rewrites while clearing stale result identity on a new failure', () => {
    const previous: TaskRecord = {
      schemaVersion: 1,
      id: 'session:module:v2:voc',
      kind: 'MODULE_ANALYSIS',
      executionStatus: 'SUCCEEDED',
      resultStatus: 'VALID',
      dependencies: [{ taskId: 'module:m2', resultFingerprint: 'm2:v1' }],
      attemptCount: 2,
      resultFingerprint: 'old-result',
      outputRef: 'blob:old-result',
      invalidation: { reason: 'changed', invalidatedAt: '2026-08-30T06:30:30.000Z' },
      moduleKey: 'voc',
      createdAt: '2026-08-30T06:00:00.000Z',
      updatedAt: '2026-08-30T06:20:00.000Z',
      endedAt: '2026-08-30T06:20:00.000Z'
    }
    const next = writeRuntimeTaskState(
      { 'session:module:v2:voc': { kind: 'module', status: 'complete', updatedAt: previous.updatedAt } },
      { [previous.id]: previous },
      previous.id,
      { kind: 'module', status: 'failed', output: 'partial', moduleKey: 'voc' },
      () => '2026-08-30T06:40:00.000Z'
    ).taskRecords[previous.id]

    expect(next.createdAt).toBe(previous.createdAt)
    expect(next.attemptCount).toBe(2)
    expect(next.dependencies).toEqual(previous.dependencies)
    expect(next.executionStatus).toBe('FAILED')
    expect(next.resultStatus).toBeUndefined()
    expect(next.resultFingerprint).toBeUndefined()
    expect(next.outputRef).toBeUndefined()
    expect(next.invalidation).toBeUndefined()
  })

  it('preserves an explicit migration/recovery timestamp', () => {
    const next = writeTaskJournalEntry(
      {},
      'source:a',
      {
        kind: 'source_clean',
        status: 'complete',
        updatedAt: '2026-08-20T03:00:00.000Z'
      },
      () => 'SHOULD_NOT_BE_USED'
    )
    expect(next['source:a'].updatedAt).toBe('2026-08-20T03:00:00.000Z')
  })

  it('removes only selected tasks without mutating the source journal', () => {
    const journal: Record<string, ProjectTaskSnapshot> = {
      'session:module:v2:voc': { kind: 'module', status: 'complete', updatedAt: '2026-08-20T00:00:00.000Z' },
      'session:module:v2:product-info': { kind: 'module', status: 'complete', updatedAt: '2026-08-20T00:00:01.000Z' },
      'session:source_clean:a': { kind: 'source_clean', status: 'complete', updatedAt: '2026-08-20T00:00:02.000Z' }
    }
    const next = removeTaskJournalEntries(journal, (taskId) => taskId.includes(':module:v2:voc'))

    expect(Object.keys(next)).toEqual([
      'session:module:v2:product-info',
      'session:source_clean:a'
    ])
    expect(journal['session:module:v2:voc']).toBeDefined()
  })

  it('removes the same selected ids from both runtime representations', () => {
    const journal: Record<string, ProjectTaskSnapshot> = {
      'session:module:v2:voc': { kind: 'module', status: 'complete', updatedAt: '2026-08-20T00:00:00.000Z' },
      'session:source_clean:a': { kind: 'source_clean', status: 'complete', updatedAt: '2026-08-20T00:00:02.000Z' }
    }
    const records = Object.fromEntries(Object.entries(journal).map(([id, snapshot]) => [
      id,
      writeRuntimeTaskState({}, {}, id, { ...snapshot }, () => snapshot.updatedAt).taskRecords[id]
    ]))
    const next = removeRuntimeTaskState(journal, records, (taskId) => taskId.includes(':module:v2:voc'))

    expect(Object.keys(next.taskJournal)).toEqual(['session:source_clean:a'])
    expect(Object.keys(next.taskRecords)).toEqual(['session:source_clean:a'])
    expect(journal['session:module:v2:voc']).toBeDefined()
    expect(records['session:module:v2:voc']).toBeDefined()
  })
})
