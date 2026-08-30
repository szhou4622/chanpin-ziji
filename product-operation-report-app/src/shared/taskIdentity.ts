export const TASK_IDENTITY_PATTERN = /^[\w.:@/+-]{1,300}$/u

export interface TaskIdentityView {
  id: string
  logicalKey?: string
  payloadKey?: string
}

export function isValidTaskIdentityKey(value: string): boolean {
  return TASK_IDENTITY_PATTERN.test(value)
}

export function assertTaskIdentityKey(value: string, label: string): void {
  if (!isValidTaskIdentityKey(value)) {
    throw new Error(`${label}格式无效`)
  }
}

/** Stable business slot. Legacy records without logicalKey fall back to their id. */
export function resolvedTaskLogicalKey(task: Pick<TaskIdentityView, 'id' | 'logicalKey'>): string {
  return task.logicalKey || task.id
}

/**
 * Builds one immutable logical-task instance id under a stable business slot.
 * The instance token should be generated once by the caller and persisted with the task.
 */
export function buildTaskInstanceId(logicalKey: string, instanceToken: string): string {
  assertTaskIdentityKey(logicalKey, '任务 logicalKey')
  if (!/^[\w.+-]{1,80}$/u.test(instanceToken)) throw new Error('任务 instanceToken 格式无效')
  const id = `${logicalKey}@${instanceToken}`
  if (!isValidTaskIdentityKey(id)) throw new Error('任务实例 ID 过长或格式无效')
  return id
}

export function taskBelongsToLogicalKey(
  task: Pick<TaskIdentityView, 'id' | 'logicalKey'>,
  logicalKey: string
): boolean {
  return resolvedTaskLogicalKey(task) === logicalKey
}
