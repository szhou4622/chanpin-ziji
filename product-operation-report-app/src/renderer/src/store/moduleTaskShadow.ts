import {
  currentTaskForLogicalKey,
  registerCurrentTask,
  type TaskCurrentIndex
} from '../../../shared/taskCurrentIndex'
import { buildTaskInstanceId } from '../../../shared/taskIdentity'
import {
  createPendingTaskRecord,
  transitionTaskExecution
} from '../../../shared/taskLifecycle'
import type { TaskRecord, TaskResultStatus } from '../../../shared/taskModel'
import type { ModuleKey } from '../../../shared/types'

export interface ModuleShadowState {
  taskRecords: Record<string, TaskRecord>
  currentTaskByLogicalKey: TaskCurrentIndex
}

export interface StartModuleShadowInput {
  logicalKey: string
  payloadKey: string
  moduleKey: ModuleKey
  inputFingerprint: string
  instanceToken: string
  now: string
}

export interface StartedModuleShadow extends ModuleShadowState {
  taskId: string
}

function replaceTask(
  taskRecords: Readonly<Record<string, TaskRecord>>,
  task: TaskRecord
): Record<string, TaskRecord> {
  return { ...taskRecords, [task.id]: task }
}

/**
 * Starts or resumes the immutable canonical Task that shadows one real model-backed
 * module execution. Existing production scheduling remains authoritative.
 */
export function startModuleShadowTask(
  taskRecords: Readonly<Record<string, TaskRecord>>,
  currentTaskByLogicalKey: Readonly<TaskCurrentIndex>,
  input: StartModuleShadowInput
): StartedModuleShadow {
  let records = { ...taskRecords }
  let currentIndex = { ...currentTaskByLogicalKey }
  let current = currentTaskForLogicalKey(records, currentIndex, input.logicalKey)

  if (current && current.executionStatus === 'RUNNING') {
    throw new Error(`模块 shadow task 已在运行：${current.id}`)
  }

  if (current && current.inputFingerprint !== input.inputFingerprint) {
    if (current.executionStatus !== 'SUCCEEDED' && current.executionStatus !== 'CANCELLED') {
      current = transitionTaskExecution(current, 'CANCELLED', input.now, { errorClass: 'INPUT_CHANGED' })
      records = replaceTask(records, current)
    }
    current = undefined
  }

  if (current) {
    if (current.executionStatus === 'PENDING') {
      const ready = transitionTaskExecution(current, 'READY', input.now)
      const running = transitionTaskExecution(ready, 'RUNNING', input.now)
      return {
        taskRecords: replaceTask(records, running),
        currentTaskByLogicalKey: currentIndex,
        taskId: running.id
      }
    }
    if (current.executionStatus === 'READY') {
      const running = transitionTaskExecution(current, 'RUNNING', input.now)
      return {
        taskRecords: replaceTask(records, running),
        currentTaskByLogicalKey: currentIndex,
        taskId: running.id
      }
    }
    if (
      current.executionStatus === 'FAILED' ||
      current.executionStatus === 'PAUSED' ||
      current.executionStatus === 'WAITING_RETRY'
    ) {
      const ready = transitionTaskExecution(current, 'READY', input.now)
      const running = transitionTaskExecution(ready, 'RUNNING', input.now)
      return {
        taskRecords: replaceTask(records, running),
        currentTaskByLogicalKey: currentIndex,
        taskId: running.id
      }
    }
  }

  const taskId = buildTaskInstanceId(input.logicalKey, input.instanceToken)
  const pending = createPendingTaskRecord({
    id: taskId,
    logicalKey: input.logicalKey,
    payloadKey: input.payloadKey,
    kind: 'MODULE_ANALYSIS',
    moduleKey: input.moduleKey,
    inputFingerprint: input.inputFingerprint
  }, input.now)
  const registered = registerCurrentTask(records, currentIndex, pending)
  const ready = transitionTaskExecution(registered.taskRecords[taskId], 'READY', input.now)
  const running = transitionTaskExecution(ready, 'RUNNING', input.now)

  return {
    taskRecords: replaceTask(registered.taskRecords, running),
    currentTaskByLogicalKey: registered.currentIndex,
    taskId
  }
}

export type ModuleShadowOutcome =
  | { executionStatus: 'SUCCEEDED'; resultStatus: Extract<TaskResultStatus, 'VALID' | 'INSUFFICIENT' | 'INVALID'> }
  | { executionStatus: 'FAILED'; errorClass?: string }
  | { executionStatus: 'CANCELLED'; errorClass?: string }

export function finishModuleShadowTask(
  taskRecords: Readonly<Record<string, TaskRecord>>,
  currentTaskByLogicalKey: Readonly<TaskCurrentIndex>,
  logicalKey: string,
  taskId: string,
  outcome: ModuleShadowOutcome,
  now: string
): ModuleShadowState {
  const current = currentTaskForLogicalKey(taskRecords, currentTaskByLogicalKey, logicalKey)
  if (!current || current.id !== taskId) {
    throw new Error(`模块 shadow task 已不是当前实例：${taskId}`)
  }
  if (current.executionStatus !== 'RUNNING') {
    throw new Error(`模块 shadow task 不是 RUNNING：${current.executionStatus}`)
  }

  const finished = outcome.executionStatus === 'SUCCEEDED'
    ? transitionTaskExecution(current, 'SUCCEEDED', now, { resultStatus: outcome.resultStatus })
    : transitionTaskExecution(current, outcome.executionStatus, now, { errorClass: outcome.errorClass })

  return {
    taskRecords: replaceTask(taskRecords, finished),
    currentTaskByLogicalKey: { ...currentTaskByLogicalKey }
  }
}

export function failCurrentRunningModuleShadowTask(
  taskRecords: Readonly<Record<string, TaskRecord>>,
  currentTaskByLogicalKey: Readonly<TaskCurrentIndex>,
  logicalKey: string,
  now: string,
  errorClass = 'UNHANDLED'
): ModuleShadowState {
  const current = currentTaskForLogicalKey(taskRecords, currentTaskByLogicalKey, logicalKey)
  if (!current || current.executionStatus !== 'RUNNING') {
    return {
      taskRecords: { ...taskRecords },
      currentTaskByLogicalKey: { ...currentTaskByLogicalKey }
    }
  }
  return finishModuleShadowTask(
    taskRecords,
    currentTaskByLogicalKey,
    logicalKey,
    current.id,
    { executionStatus: 'FAILED', errorClass },
    now
  )
}
