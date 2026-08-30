import {
  isValidTaskIdentityKey,
  resolvedTaskLogicalKey
} from './taskIdentity'
import type { TaskRecord } from './taskModel'

export type TaskCurrentIndex = Record<string, string>

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

export function sanitizeTaskCurrentIndex(
  value: unknown,
  taskRecords: Readonly<Record<string, TaskRecord>>
): TaskCurrentIndex {
  if (!isPlainObject(value)) return {}
  const result: TaskCurrentIndex = {}
  for (const [logicalKey, rawTaskId] of Object.entries(value)) {
    if (!isValidTaskIdentityKey(logicalKey) || typeof rawTaskId !== 'string' || !isValidTaskIdentityKey(rawTaskId)) continue
    const task = taskRecords[rawTaskId]
    if (!task || resolvedTaskLogicalKey(task) !== logicalKey) continue
    result[logicalKey] = rawTaskId
  }
  return result
}

export function currentTaskForLogicalKey(
  taskRecords: Readonly<Record<string, TaskRecord>>,
  currentIndex: Readonly<TaskCurrentIndex>,
  logicalKey: string
): TaskRecord | undefined {
  const taskId = currentIndex[logicalKey]
  if (!taskId) return undefined
  const task = taskRecords[taskId]
  return task && resolvedTaskLogicalKey(task) === logicalKey ? task : undefined
}

function mayBeReplaced(task: TaskRecord): boolean {
  return task.executionStatus === 'SUCCEEDED' || task.executionStatus === 'CANCELLED'
}

function sameImmutableTaskIdentity(left: TaskRecord, right: TaskRecord): boolean {
  return (
    left.id === right.id &&
    resolvedTaskLogicalKey(left) === resolvedTaskLogicalKey(right) &&
    left.payloadKey === right.payloadKey &&
    left.kind === right.kind &&
    left.inputFingerprint === right.inputFingerprint &&
    left.sourceId === right.sourceId &&
    left.moduleKey === right.moduleKey &&
    left.createdAt === right.createdAt
  )
}

export interface RegisterCurrentTaskResult {
  taskRecords: Record<string, TaskRecord>
  currentIndex: TaskCurrentIndex
}

/**
 * Registers one immutable Task instance as the current instance for its stable logical slot.
 * A live/retryable current task must be resolved or cancelled before another instance can replace it.
 */
export function registerCurrentTask(
  taskRecords: Readonly<Record<string, TaskRecord>>,
  currentIndex: Readonly<TaskCurrentIndex>,
  task: TaskRecord
): RegisterCurrentTaskResult {
  const logicalKey = resolvedTaskLogicalKey(task)
  if (!isValidTaskIdentityKey(task.id) || !isValidTaskIdentityKey(logicalKey)) {
    throw new Error('任务身份格式无效')
  }

  const existingById = taskRecords[task.id]
  if (existingById && !sameImmutableTaskIdentity(existingById, task)) {
    throw new Error(`任务实例 ID 已存在且身份不一致：${task.id}`)
  }
  const registeredTask = existingById || task

  const current = currentTaskForLogicalKey(taskRecords, currentIndex, logicalKey)
  if (current && current.id !== registeredTask.id && !mayBeReplaced(current)) {
    throw new Error(`当前任务 ${current.id} 尚未进入可替换终态`)
  }

  return {
    taskRecords: existingById ? { ...taskRecords } : { ...taskRecords, [task.id]: task },
    currentIndex: { ...currentIndex, [logicalKey]: registeredTask.id }
  }
}

/** Clear only the pointer the caller actually observed; never erase a newer replacement by accident. */
export function clearCurrentTask(
  currentIndex: Readonly<TaskCurrentIndex>,
  logicalKey: string,
  expectedTaskId: string
): TaskCurrentIndex {
  if (currentIndex[logicalKey] !== expectedTaskId) return { ...currentIndex }
  const next = { ...currentIndex }
  delete next[logicalKey]
  return next
}
