import type { ModuleKey, ModuleRunState } from '../../../shared/types'
import type { TaskRecord } from '../../../shared/taskModel'
import {
  writeRuntimeTaskState,
  type TaskJournal
} from './taskJournalAdapter'

export interface InsufficientModuleOutcome {
  taskJournal: TaskJournal
  taskRecords: Record<string, TaskRecord>
  moduleState: ModuleRunState
  output: string
}

function normalizeInsufficientMessage(message: string): string {
  const value = message.trim()
  if (!value) return '暂无分析：现有资料不足。'
  return value.startsWith('暂无分析') ? value : `暂无分析：${value}`
}

/**
 * One canonical completion path for a module that ran to a legitimate
 * evidence-insufficient business result without producing a normal artifact.
 */
export function completeModuleAsInsufficient(
  journal: Readonly<TaskJournal>,
  taskRecords: Readonly<Record<string, TaskRecord>>,
  taskId: string,
  moduleKey: ModuleKey,
  message: string,
  updatedAt: string,
  inputFingerprint?: string
): InsufficientModuleOutcome {
  const output = normalizeInsufficientMessage(message)
  const taskState = writeRuntimeTaskState(journal, taskRecords, taskId, {
    kind: 'module',
    status: 'complete',
    output,
    inputFingerprint,
    resultStatus: 'INSUFFICIENT',
    moduleKey,
    updatedAt
  })
  return {
    ...taskState,
    moduleState: {
      status: 'skipped',
      message: output,
      updatedAt
    },
    output
  }
}
