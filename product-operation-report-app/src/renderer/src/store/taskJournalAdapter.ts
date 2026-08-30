import type { ProjectTaskSnapshot } from '../../../shared/types'

export type TaskJournal = Record<string, ProjectTaskSnapshot>

export type TaskJournalWrite = Omit<ProjectTaskSnapshot, 'updatedAt'> & {
  updatedAt?: string
}

/**
 * Compatibility write boundary for the legacy production taskJournal.
 *
 * Keep runtime journal mutations behind this adapter until canonical TaskRecord
 * becomes the authoritative writer. This makes the eventual authority switch a
 * single implementation change instead of another store-wide refactor.
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

export function removeTaskJournalEntries(
  journal: Readonly<TaskJournal>,
  shouldRemove: (taskId: string, snapshot: ProjectTaskSnapshot) => boolean
): TaskJournal {
  return Object.fromEntries(
    Object.entries(journal).filter(([taskId, snapshot]) => !shouldRemove(taskId, snapshot))
  )
}
