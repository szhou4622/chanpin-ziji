import { describe, expect, it } from 'vitest'
import { createPendingTaskRecord, transitionTaskExecution } from './taskLifecycle'

describe('canonical task lifecycle', () => {
  it('creates a durable PENDING logical task without inventing an attempt', () => {
    const task = createPendingTaskRecord({
      id: 'session:module:v2:product-info',
      kind: 'MODULE_ANALYSIS',
      moduleKey: 'product-info',
      dependencies: []
    }, '2026-08-30T08:20:00.000Z')

    expect(task).toMatchObject({
      executionStatus: 'PENDING',
      attemptCount: 0,
      createdAt: '2026-08-30T08:20:00.000Z',
      updatedAt: '2026-08-30T08:20:00.000Z',
      migratedFromLegacy: false
    })
    expect(task.resultStatus).toBeUndefined()
  })

  it('supports ready-run-wait-retry-run-success while keeping attempt counting separate', () => {
    const pending = createPendingTaskRecord({
      id: 'session:module:v2:voc',
      kind: 'MODULE_ANALYSIS',
      moduleKey: 'voc'
    }, '2026-08-30T08:20:00.000Z')
    const ready = transitionTaskExecution(pending, 'READY', '2026-08-30T08:21:00.000Z')
    const running = transitionTaskExecution(ready, 'RUNNING', '2026-08-30T08:22:00.000Z')
    const waiting = transitionTaskExecution(running, 'WAITING_RETRY', '2026-08-30T08:23:00.000Z', {
      retryAt: '2026-08-30T08:25:00.000Z',
      errorClass: 'NETWORK'
    })
    const readyAgain = transitionTaskExecution(waiting, 'READY', '2026-08-30T08:25:00.000Z')
    const runningAgain = transitionTaskExecution(readyAgain, 'RUNNING', '2026-08-30T08:26:00.000Z')
    const succeeded = transitionTaskExecution(runningAgain, 'SUCCEEDED', '2026-08-30T08:27:00.000Z', {
      resultStatus: 'VALID',
      resultFingerprint: 'result:v1',
      outputRef: 'blob:result-v1'
    })

    expect(running.startedAt).toBe('2026-08-30T08:22:00.000Z')
    expect(waiting).toMatchObject({
      executionStatus: 'WAITING_RETRY',
      retryAt: '2026-08-30T08:25:00.000Z',
      errorClass: 'NETWORK'
    })
    expect(readyAgain.retryAt).toBeUndefined()
    expect(readyAgain.startedAt).toBeUndefined()
    expect(runningAgain.startedAt).toBe('2026-08-30T08:26:00.000Z')
    expect(succeeded).toMatchObject({
      executionStatus: 'SUCCEEDED',
      resultStatus: 'VALID',
      resultFingerprint: 'result:v1',
      outputRef: 'blob:result-v1',
      endedAt: '2026-08-30T08:27:00.000Z',
      attemptCount: 0
    })
  })

  it('allows explicit retry from FAILED and resume from PAUSED, but not from CANCELLED', () => {
    const pending = createPendingTaskRecord({ id: 'task:a', kind: 'MODULE_ANALYSIS' }, '2026-08-30T08:20:00.000Z')
    const ready = transitionTaskExecution(pending, 'READY', '2026-08-30T08:21:00.000Z')
    const running = transitionTaskExecution(ready, 'RUNNING', '2026-08-30T08:22:00.000Z')
    const failed = transitionTaskExecution(running, 'FAILED', '2026-08-30T08:23:00.000Z', { errorClass: 'UPSTREAM_5XX' })
    expect(transitionTaskExecution(failed, 'READY', '2026-08-30T08:24:00.000Z').executionStatus).toBe('READY')

    const paused = transitionTaskExecution(running, 'PAUSED', '2026-08-30T08:23:30.000Z', { errorClass: 'APP_EXIT' })
    expect(transitionTaskExecution(paused, 'READY', '2026-08-30T08:24:30.000Z').executionStatus).toBe('READY')

    const cancelled = transitionTaskExecution(running, 'CANCELLED', '2026-08-30T08:25:00.000Z')
    expect(() => transitionTaskExecution(cancelled, 'READY', '2026-08-30T08:26:00.000Z')).toThrow(/非法任务状态转换/u)
  })

  it('rejects transitions that skip the scheduler claim boundary', () => {
    const pending = createPendingTaskRecord({ id: 'task:a', kind: 'MODULE_ANALYSIS' }, '2026-08-30T08:20:00.000Z')
    expect(() => transitionTaskExecution(pending, 'RUNNING', '2026-08-30T08:21:00.000Z')).toThrow(/PENDING → RUNNING/u)

    const ready = transitionTaskExecution(pending, 'READY', '2026-08-30T08:21:00.000Z')
    expect(() => transitionTaskExecution(ready, 'SUCCEEDED', '2026-08-30T08:22:00.000Z', { resultStatus: 'VALID' })).toThrow(/READY → SUCCEEDED/u)
  })

  it('requires an explicit future retry time and an explicit completion result', () => {
    const pending = createPendingTaskRecord({ id: 'task:a', kind: 'MODULE_ANALYSIS' }, '2026-08-30T08:20:00.000Z')
    const running = transitionTaskExecution(
      transitionTaskExecution(pending, 'READY', '2026-08-30T08:21:00.000Z'),
      'RUNNING',
      '2026-08-30T08:22:00.000Z'
    )

    expect(() => transitionTaskExecution(running, 'WAITING_RETRY', '2026-08-30T08:23:00.000Z')).toThrow(/retryAt/u)
    expect(() => transitionTaskExecution(running, 'WAITING_RETRY', '2026-08-30T08:23:00.000Z', {
      retryAt: '2026-08-30T08:22:59.000Z'
    })).toThrow(/不能早于/u)
    expect(() => transitionTaskExecution(running, 'SUCCEEDED', '2026-08-30T08:24:00.000Z')).toThrow(/必须提供/u)
    expect(() => transitionTaskExecution(running, 'SUCCEEDED', '2026-08-30T08:24:00.000Z', {
      resultStatus: 'STALE'
    })).toThrow(/VALID、INSUFFICIENT 或 INVALID/u)
  })
})
