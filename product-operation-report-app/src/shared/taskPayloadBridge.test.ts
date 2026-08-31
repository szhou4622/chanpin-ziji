import { describe, expect, it } from 'vitest'
import { reconcileTaskRecordMirror, type TaskRecord } from './taskModel'
import type { ProjectTaskSnapshot } from './types'

const payloadKey = 'session-a:module:v2:voc'
const shadowId = `${payloadKey}@run-a`
const updatedAt = '2026-08-31T12:10:00.000Z'

function payload(overrides: Partial<ProjectTaskSnapshot> = {}): ProjectTaskSnapshot {
  return {
    kind: 'module',
    status: 'complete',
    output: 'VOC 完整输出',
    inputFingerprint: 'input:v1',
    updatedAt,
    ...overrides
  }
}

function shadow(overrides: Partial<TaskRecord> = {}): TaskRecord {
  return {
    schemaVersion: 1,
    id: shadowId,
    logicalKey: payloadKey,
    payloadKey,
    kind: 'MODULE_ANALYSIS',
    executionStatus: 'SUCCEEDED',
    resultStatus: 'VALID',
    dependencies: [],
    inputFingerprint: 'input:v1',
    moduleKey: 'voc',
    attemptCount: 0,
    createdAt: '2026-08-31T12:00:00.000Z',
    updatedAt,
    startedAt: '2026-08-31T12:01:00.000Z',
    endedAt: updatedAt,
    migratedFromLegacy: false,
    ...overrides
  }
}

describe('payload-backed completed canonical task recovery', () => {
  it('preserves a completed shadow task only when its legacy payload proves the same mutation', () => {
    const recovered = reconcileTaskRecordMirror(
      { [payloadKey]: payload() },
      { [shadowId]: shadow() }
    )

    expect(recovered[shadowId]).toMatchObject({
      id: shadowId,
      logicalKey: payloadKey,
      payloadKey,
      executionStatus: 'SUCCEEDED',
      resultStatus: 'VALID',
      inputFingerprint: 'input:v1',
      updatedAt
    })
    expect(recovered[payloadKey]).toBeDefined()
  })

  it('drops a completed shadow task when the payload timestamp does not match', () => {
    const recovered = reconcileTaskRecordMirror(
      { [payloadKey]: payload({ updatedAt: '2026-08-31T12:09:59.000Z' }) },
      { [shadowId]: shadow() }
    )
    expect(recovered[shadowId]).toBeUndefined()
  })

  it('drops a completed shadow task when the payload input fingerprint does not match', () => {
    const recovered = reconcileTaskRecordMirror(
      { [payloadKey]: payload({ inputFingerprint: 'input:v2' }) },
      { [shadowId]: shadow() }
    )
    expect(recovered[shadowId]).toBeUndefined()
  })

  it('drops a completed shadow task when the payload is not complete', () => {
    const recovered = reconcileTaskRecordMirror(
      { [payloadKey]: payload({ status: 'failed' }) },
      { [shadowId]: shadow() }
    )
    expect(recovered[shadowId]).toBeUndefined()
  })

  it('does not restore a completed canonical-only task with no payloadKey', () => {
    const recovered = reconcileTaskRecordMirror(
      { [payloadKey]: payload() },
      { [shadowId]: shadow({ payloadKey: undefined }) }
    )
    expect(recovered[shadowId]).toBeUndefined()
  })
})
