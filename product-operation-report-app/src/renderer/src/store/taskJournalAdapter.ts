import type { ModuleKey, ProjectTaskSnapshot } from '../../../shared/types'
import {
  projectLegacyTaskSnapshot,
  type TaskRecord,
  type TaskResultStatus
} from '../../../shared/taskModel'

export type TaskJournal = Record<string, ProjectTaskSnapshot>
export type TaskRecordMap = Record<string, TaskRecord>

export type TaskJournalWrite = Omit<ProjectTaskSnapshot, 'updatedAt'> & {
  updatedAt?: string
}

export type RuntimeTaskWrite = TaskJournalWrite & {
  resultStatus?: TaskResultStatus
  sourceId?: string
  moduleKey?: ModuleKey
}

export interface RuntimeTaskState {
  taskJournal: TaskJournal
  taskRecords: TaskRecordMap
}

/**
 * Compatibility write boundary for the legacy production taskJournal.
 *
 * Keep runtime journal mutations behind this adapter until canonical TaskRecord
 * becomes the authoritative read/write source. During the dual-write bridge one
 * mutation produces both representations with exactly the same updatedAt.
 */
export function writeTaskJournalEntry(
  journal: Readonly<TaskJournal>,
  taskId: string,
  value: TaskJournalWrite,
  now: () => string = () => new Date().toISOString()
): TaskJournal {
  return {
    ...journal,
    [taskId]: {
      ...value,
      updatedAt: value.updatedAt || now()
    }
  }
}

export function writeRuntimeTaskState(
  journal: Readonly<TaskJournal>,
  taskRecords: Readonly<TaskRecordMap>,
  taskId: string,
  value: RuntimeTaskWrite,
  now: () => string = () => new Date().toISOString()
): RuntimeTaskState {
  const timestamp = value.updatedAt || now()
  const { resultStatus, sourceId, moduleKey, ...journalValue } = value
  const taskJournal = writeTaskJournalEntry(journal, taskId, { ...journalValue, updatedAt: timestamp }, () => timestamp)
  const snapshot = taskJournal[taskId]
  const projected = projectLegacyTaskSnapshot(taskId, snapshot).task
  const previous = taskRecords[taskId]
  const executionSucceeded = projected.executionStatus === 'SUCCEEDED'
  const canonical: TaskRecord = {
    ...projected,
    resultStatus: executionSucceeded ? resultStatus || projected.resultStatus : undefined,
    dependencies: previous?.dependencies || projected.dependencies,
    sourceId: sourceId || previous?.sourceId,
    moduleKey: moduleKey || previous?.moduleKey,
    attemptCount: previous?.attemptCount ?? projected.attemptCount,
    createdAt: previous?.createdAt || timestamp,
    updatedAt: timestamp,
    migratedFromLegacy: false
  }
  delete canonical.resultFingerprint
  delete canonical.outputRef
  delete canonical.invalidation
  if (canonical.executionStatus !== 'WAITING_RETRY') delete canonical.retryAt
  if (canonical.executionStatus !== 'RUNNING') delete canonical.startedAt

  return {
    taskJournal,
    taskRecords: { ...taskRecords, [taskId]: canonical }
  }
}

export function removeTaskJournalEntries(
  journal: Readonly<TaskJournal>,
  shouldRemove: (taskId: string, snapshot: ProjectTaskSnapshot) => boolean
): TaskJournal {
  return Object.fromEntries(
    Object.entries(journal).filter(([taskId, snapshot]) => !shouldRemove(taskId, snapshot))
  )
}

export function removeRuntimeTaskState(
  journal: Readonly<TaskJournal>,
  taskRecords: Readonly<TaskRecordMap>,
  shouldRemove: (taskId: string, snapshot: ProjectTaskSnapshot) => boolean
): RuntimeTaskState {
  const removedIds = new Set(
    Object.entries(journal).flatMap(([taskId, snapshot]) => shouldRemove(taskId, snapshot) ? [taskId] : [])
  )
  return {
    taskJournal: removeTaskJournalEntries(journal, (taskId) => removedIds.has(taskId)),
    taskRecords: Object.fromEntries(Object.entries(taskRecords).filter(([taskId]) => !removedIds.has(taskId)))
  }
}
