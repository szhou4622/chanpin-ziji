import { describe, expect, it } from 'vitest'
import { createPendingTaskRecord, transitionTaskExecution } from './taskLifecycle'
import {
  clearCurrentTask,
  currentTaskForLogicalKey,
  registerCurrentTask,
  sanitizeTaskCurrentIndex
} from './taskCurrentIndex'

function pending(id: string, logicalKey: string) {
  return createPendingTaskRecord({ id, logicalKey, kind: 'MODULE_ANALYSIS', moduleKey: 'voc' }, '2026-08-30T08:00:00.000Z')
}

describe('current task index', () => {
  it('resolves only an explicit pointer and never guesses by timestamp', () => {
    const oldTask = pending('slot:voc@old', 'slot:voc')
    const newTask = pending('slot:voc@new', 'slot:voc')
    const records = { [oldTask.id]: oldTask, [newTask.id]: newTask }

    expect(currentTaskForLogicalKey(records, {}, 'slot:voc')).toBeUndefined()
    expect(currentTaskForLogicalKey(records, { 'slot:voc': oldTask.id }, 'slot:voc')?.id).toBe(oldTask.id)
  })

  it('rejects switching away from a live or retryable current task', () => {
    const first = pending('slot:voc@a', 'slot:voc')
    const second = pending('slot:voc@b', 'slot:voc')
    const registered = registerCurrentTask({}, {}, first)

    expect(() => registerCurrentTask(registered.taskRecords, registered.currentIndex, second)).toThrow(/尚未进入可替换终态/u)

    const ready = transitionTaskExecution(first, 'READY', '2026-08-30T08:01:00.000Z')
    const running = transitionTaskExecution(ready, 'RUNNING', '2026-08-30T08:02:00.000Z')
    const failed = transitionTaskExecution(running, 'FAILED', '2026-08-30T08:03:00.000Z')
    expect(() => registerCurrentTask({ [failed.id]: failed }, { 'slot:voc': failed.id }, second)).toThrow(/尚未进入可替换终态/u)
  })

  it('allows a new instance after the previous current task is terminal', () => {
    const first = pending('slot:voc@a', 'slot:voc')
    const ready = transitionTaskExecution(first, 'READY', '2026-08-30T08:01:00.000Z')
    const running = transitionTaskExecution(ready, 'RUNNING', '2026-08-30T08:02:00.000Z')
    const succeeded = transitionTaskExecution(running, 'SUCCEEDED', '2026-08-30T08:03:00.000Z', { resultStatus: 'VALID' })
    const second = pending('slot:voc@b', 'slot:voc')

    const replaced = registerCurrentTask(
      { [succeeded.id]: succeeded },
      { 'slot:voc': succeeded.id },
      second
    )
    expect(replaced.currentIndex['slot:voc']).toBe(second.id)
    expect(replaced.taskRecords[succeeded.id].executionStatus).toBe('SUCCEEDED')
    expect(replaced.taskRecords[second.id].executionStatus).toBe('PENDING')
  })

  it('sanitizes persisted pointers and drops missing or cross-slot references', () => {
    const task = pending('slot:voc@a', 'slot:voc')
    const sanitized = sanitizeTaskCurrentIndex({
      'slot:voc': task.id,
      'slot:other': task.id,
      'missing:slot': 'missing:slot@a',
      'bad logical key': task.id
    }, { [task.id]: task })

    expect(sanitized).toEqual({ 'slot:voc': task.id })
  })

  it('clears a pointer only when the caller still owns the observed task id', () => {
    expect(clearCurrentTask({ 'slot:voc': 'slot:voc@new' }, 'slot:voc', 'slot:voc@old')).toEqual({
      'slot:voc': 'slot:voc@new'
    })
    expect(clearCurrentTask({ 'slot:voc': 'slot:voc@new' }, 'slot:voc', 'slot:voc@new')).toEqual({})
  })
})
