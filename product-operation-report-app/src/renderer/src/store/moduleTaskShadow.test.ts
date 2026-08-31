import { describe, expect, it } from 'vitest'
import { transitionTaskExecution } from '../../../shared/taskLifecycle'
import {
  failCurrentRunningModuleShadowTask,
  finishModuleShadowTask,
  startModuleShadowTask
} from './moduleTaskShadow'

const logicalKey = 'session-a:module:v2:voc'
const payloadKey = logicalKey

function start(
  taskRecords = {},
  currentTaskByLogicalKey = {},
  fingerprint = 'input:v1',
  token = 'run-a',
  now = '2026-08-31T12:00:00.000Z'
) {
  return startModuleShadowTask(taskRecords, currentTaskByLogicalKey, {
    logicalKey,
    payloadKey,
    moduleKey: 'voc',
    inputFingerprint: fingerprint,
    instanceToken: token,
    now
  })
}

describe('module shadow lifecycle', () => {
  it('creates one immutable task instance and advances it to RUNNING', () => {
    const started = start()
    expect(started.currentTaskByLogicalKey[logicalKey]).toBe(started.taskId)
    expect(started.taskRecords[started.taskId]).toMatchObject({
      id: started.taskId,
      logicalKey,
      payloadKey,
      moduleKey: 'voc',
      inputFingerprint: 'input:v1',
      executionStatus: 'RUNNING'
    })
  })

  it('resumes the same FAILED task when the input fingerprint is unchanged', () => {
    const first = start()
    const failed = finishModuleShadowTask(
      first.taskRecords,
      first.currentTaskByLogicalKey,
      logicalKey,
      first.taskId,
      { executionStatus: 'FAILED', errorClass: 'UPSTREAM_5XX' },
      '2026-08-31T12:01:00.000Z'
    )

    const resumed = start(
      failed.taskRecords,
      failed.currentTaskByLogicalKey,
      'input:v1',
      'unused-new-token',
      '2026-08-31T12:02:00.000Z'
    )
    expect(resumed.taskId).toBe(first.taskId)
    expect(resumed.taskRecords[first.taskId].executionStatus).toBe('RUNNING')
  })

  it('cancels a failed task and creates a replacement when the input changed', () => {
    const first = start()
    const failed = finishModuleShadowTask(
      first.taskRecords,
      first.currentTaskByLogicalKey,
      logicalKey,
      first.taskId,
      { executionStatus: 'FAILED' },
      '2026-08-31T12:01:00.000Z'
    )
    const replaced = start(
      failed.taskRecords,
      failed.currentTaskByLogicalKey,
      'input:v2',
      'run-b',
      '2026-08-31T12:02:00.000Z'
    )

    expect(replaced.taskId).not.toBe(first.taskId)
    expect(replaced.taskRecords[first.taskId]).toMatchObject({
      executionStatus: 'CANCELLED',
      errorClass: 'INPUT_CHANGED'
    })
    expect(replaced.currentTaskByLogicalKey[logicalKey]).toBe(replaced.taskId)
  })

  it('keeps a succeeded task immutable and creates a new instance for a forced rerun', () => {
    const first = start()
    const succeeded = finishModuleShadowTask(
      first.taskRecords,
      first.currentTaskByLogicalKey,
      logicalKey,
      first.taskId,
      { executionStatus: 'SUCCEEDED', resultStatus: 'VALID' },
      '2026-08-31T12:01:00.000Z'
    )
    const rerun = start(
      succeeded.taskRecords,
      succeeded.currentTaskByLogicalKey,
      'input:v1',
      'run-b',
      '2026-08-31T12:02:00.000Z'
    )

    expect(rerun.taskId).not.toBe(first.taskId)
    expect(rerun.taskRecords[first.taskId]).toMatchObject({
      executionStatus: 'SUCCEEDED',
      resultStatus: 'VALID'
    })
  })

  it('records explicit user stop as CANCELLED rather than FAILED', () => {
    const first = start()
    const cancelled = finishModuleShadowTask(
      first.taskRecords,
      first.currentTaskByLogicalKey,
      logicalKey,
      first.taskId,
      { executionStatus: 'CANCELLED', errorClass: 'USER_STOP' },
      '2026-08-31T12:01:00.000Z'
    )
    expect(cancelled.taskRecords[first.taskId]).toMatchObject({
      executionStatus: 'CANCELLED',
      errorClass: 'USER_STOP'
    })
  })

  it('fails closed if a second model execution tries to start while current is RUNNING', () => {
    const first = start()
    expect(() => start(
      first.taskRecords,
      first.currentTaskByLogicalKey,
      'input:v1',
      'run-b',
      '2026-08-31T12:00:30.000Z'
    )).toThrow(/已在运行/u)
  })

  it('can fail the current RUNNING shadow task from an outer rejected-promise boundary', () => {
    const first = start()
    const failed = failCurrentRunningModuleShadowTask(
      first.taskRecords,
      first.currentTaskByLogicalKey,
      logicalKey,
      '2026-08-31T12:01:00.000Z',
      'UNHANDLED'
    )
    expect(failed.taskRecords[first.taskId]).toMatchObject({
      executionStatus: 'FAILED',
      errorClass: 'UNHANDLED'
    })
  })

  it('does not mutate a non-running current task during outer failure cleanup', () => {
    const first = start()
    const failedTask = transitionTaskExecution(
      first.taskRecords[first.taskId],
      'FAILED',
      '2026-08-31T12:01:00.000Z'
    )
    const cleaned = failCurrentRunningModuleShadowTask(
      { ...first.taskRecords, [first.taskId]: failedTask },
      first.currentTaskByLogicalKey,
      logicalKey,
      '2026-08-31T12:02:00.000Z'
    )
    expect(cleaned.taskRecords[first.taskId].executionStatus).toBe('FAILED')
  })
})
