import type {
  TaskDependencySnapshot,
  TaskExecutionStatus,
  TaskKind,
  TaskRecord,
  TaskResultStatus
} from './taskModel'
import type { ModuleKey } from './types'

export interface CreatePendingTaskInput {
  id: string
  kind: TaskKind
  dependencies?: TaskDependencySnapshot[]
  inputFingerprint?: string
  sourceId?: string
  moduleKey?: ModuleKey
}

export interface TaskTransitionOptions {
  resultStatus?: TaskResultStatus
  resultFingerprint?: string
  outputRef?: string
  retryAt?: string
  errorClass?: string
}

const ALLOWED_TRANSITIONS: Record<TaskExecutionStatus, ReadonlySet<TaskExecutionStatus>> = {
  PENDING: new Set(['READY', 'PAUSED', 'CANCELLED']),
  READY: new Set(['RUNNING', 'PAUSED', 'CANCELLED']),
  RUNNING: new Set(['WAITING_RETRY', 'PAUSED', 'SUCCEEDED', 'FAILED', 'CANCELLED']),
  WAITING_RETRY: new Set(['READY', 'PAUSED', 'CANCELLED']),
  PAUSED: new Set(['READY', 'CANCELLED']),
  SUCCEEDED: new Set(),
  FAILED: new Set(['READY', 'CANCELLED']),
  CANCELLED: new Set()
}

const COMPLETION_RESULT_STATUSES = new Set<TaskResultStatus>(['VALID', 'INSUFFICIENT', 'INVALID'])

function assertIsoDate(value: string, label: string): void {
  if (!Number.isFinite(Date.parse(value))) throw new Error(`${label}不是有效时间`)
}

export function createPendingTaskRecord(
  input: CreatePendingTaskInput,
  now: string = new Date().toISOString()
): TaskRecord {
  assertIsoDate(now, '任务创建时间')
  return {
    schemaVersion: 1,
    id: input.id,
    kind: input.kind,
    executionStatus: 'PENDING',
    dependencies: [...(input.dependencies || [])],
    inputFingerprint: input.inputFingerprint,
    sourceId: input.sourceId,
    moduleKey: input.moduleKey,
    attemptCount: 0,
    createdAt: now,
    updatedAt: now,
    migratedFromLegacy: false
  }
}

/**
 * Canonical execution-state transition boundary.
 * Attempt counting remains owned by the future Attempt Manager; this reducer only
 * governs the durable logical Task lifecycle.
 */
export function transitionTaskExecution(
  task: TaskRecord,
  nextStatus: TaskExecutionStatus,
  now: string = new Date().toISOString(),
  options: TaskTransitionOptions = {}
): TaskRecord {
  assertIsoDate(now, '任务状态时间')
  if (Date.parse(now) < Date.parse(task.updatedAt)) {
    throw new Error('任务状态时间不能早于当前 updatedAt')
  }
  if (!ALLOWED_TRANSITIONS[task.executionStatus].has(nextStatus)) {
    throw new Error(`非法任务状态转换：${task.executionStatus} → ${nextStatus}`)
  }

  if (nextStatus === 'WAITING_RETRY') {
    if (!options.retryAt) throw new Error('WAITING_RETRY 必须提供 retryAt')
    assertIsoDate(options.retryAt, 'retryAt')
    if (Date.parse(options.retryAt) < Date.parse(now)) {
      throw new Error('WAITING_RETRY 的 retryAt 不能早于当前状态时间')
    }
  } else if (options.retryAt) {
    throw new Error(`${nextStatus} 不能携带 retryAt`)
  }

  if (nextStatus === 'SUCCEEDED') {
    if (!options.resultStatus || !COMPLETION_RESULT_STATUSES.has(options.resultStatus)) {
      throw new Error('SUCCEEDED 必须提供 VALID、INSUFFICIENT 或 INVALID 结果状态')
    }
  } else {
    if (options.resultStatus) throw new Error(`${nextStatus} 不能携带 resultStatus`)
    if (options.resultFingerprint) throw new Error(`${nextStatus} 不能携带 resultFingerprint`)
    if (options.outputRef) throw new Error(`${nextStatus} 不能携带 outputRef`)
  }

  const next: TaskRecord = {
    ...task,
    executionStatus: nextStatus,
    updatedAt: now,
    resultStatus: undefined,
    resultFingerprint: undefined,
    outputRef: undefined,
    invalidation: undefined,
    retryAt: undefined,
    errorClass: undefined,
    endedAt: undefined
  }

  if (nextStatus === 'READY') {
    next.startedAt = undefined
  } else if (nextStatus === 'RUNNING') {
    next.startedAt = now
  } else if (nextStatus === 'WAITING_RETRY') {
    next.retryAt = options.retryAt
    next.errorClass = options.errorClass
  } else if (nextStatus === 'SUCCEEDED') {
    next.resultStatus = options.resultStatus
    next.resultFingerprint = options.resultFingerprint
    next.outputRef = options.outputRef
    next.endedAt = now
    next.errorClass = undefined
  } else if (nextStatus === 'FAILED') {
    next.errorClass = options.errorClass
    next.endedAt = now
  } else if (nextStatus === 'CANCELLED') {
    next.errorClass = options.errorClass
    next.endedAt = now
  } else if (nextStatus === 'PAUSED') {
    next.errorClass = options.errorClass
  }

  return next
}
