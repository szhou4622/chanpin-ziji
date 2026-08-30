import type { ModuleKey, ProjectTaskSnapshot } from './types'

export const TASK_EXECUTION_STATUSES = [
  'PENDING',
  'READY',
  'RUNNING',
  'WAITING_RETRY',
  'PAUSED',
  'SUCCEEDED',
  'FAILED',
  'CANCELLED'
] as const

export type TaskExecutionStatus = (typeof TASK_EXECUTION_STATUSES)[number]

export const TASK_RESULT_STATUSES = ['VALID', 'STALE', 'INSUFFICIENT', 'INVALID'] as const
export type TaskResultStatus = (typeof TASK_RESULT_STATUSES)[number]

export const TASK_KINDS = [
  'SOURCE_PARSE',
  'SOURCE_CLEAN',
  'MODULE_ANALYSIS',
  'REPORT_ASSEMBLE',
  'LEGACY_SUMMARY',
  'LEGACY_ANALYSIS_STEP',
  'LEGACY_FINAL_PART'
] as const

export type TaskKind = (typeof TASK_KINDS)[number]

export const ATTEMPT_STATUSES = [
  'CREATED',
  'RUNNING',
  'UNKNOWN',
  'SUCCEEDED',
  'FAILED',
  'CANCELLED'
] as const

export type AttemptStatus = (typeof ATTEMPT_STATUSES)[number]

export interface TaskDependencySnapshot {
  taskId: string
  resultFingerprint: string
}

export interface TaskInvalidation {
  reason: string
  invalidatedBy?: string
  invalidatedAt: string
}

/**
 * Canonical durable task model for the v2 engine.
 * Large outputs remain outside the record and are referenced through outputRef.
 */
export interface TaskRecord {
  schemaVersion: 1
  id: string
  kind: TaskKind
  executionStatus: TaskExecutionStatus
  resultStatus?: TaskResultStatus
  dependencies: TaskDependencySnapshot[]
  inputFingerprint?: string
  resultFingerprint?: string
  sourceId?: string
  moduleKey?: ModuleKey
  attemptCount: number
  errorClass?: string
  retryAt?: string
  outputRef?: string
  invalidation?: TaskInvalidation
  createdAt: string
  updatedAt: string
  startedAt?: string
  endedAt?: string
  migratedFromLegacy?: boolean
}

/**
 * One logical task may have multiple transport/provider attempts.
 * UNKNOWN is intentionally distinct from FAILED: a disconnected request must be reconciled before replacement.
 */
export interface TaskAttemptRecord {
  schemaVersion: 1
  id: string
  taskId: string
  attempt: number
  status: AttemptStatus
  requestId?: string
  billingLogicalId?: string
  model?: string
  providerRoute?: string
  startedAt?: string
  endedAt?: string
  errorClass?: string
}

const LEGACY_KIND_MAP: Record<ProjectTaskSnapshot['kind'], TaskKind> = {
  parse: 'SOURCE_PARSE',
  source_clean: 'SOURCE_CLEAN',
  module: 'MODULE_ANALYSIS',
  summary: 'LEGACY_SUMMARY',
  analysis_step: 'LEGACY_ANALYSIS_STEP',
  final_part: 'LEGACY_FINAL_PART'
}

const LEGACY_EXECUTION_MAP: Record<ProjectTaskSnapshot['status'], TaskExecutionStatus> = {
  complete: 'SUCCEEDED',
  failed: 'FAILED',
  interrupted: 'PAUSED'
}

export interface LegacyTaskProjection {
  task: TaskRecord
  /** Retained separately until Artifact/Blob references replace legacy inline outputs. */
  legacyOutput?: string
}

/**
 * Deterministic compatibility projection. It never calls a model and never rewrites legacy output content.
 */
export function projectLegacyTaskSnapshot(taskId: string, snapshot: ProjectTaskSnapshot): LegacyTaskProjection {
  const executionStatus = LEGACY_EXECUTION_MAP[snapshot.status]
  return {
    task: {
      schemaVersion: 1,
      id: taskId,
      kind: LEGACY_KIND_MAP[snapshot.kind],
      executionStatus,
      resultStatus: executionStatus === 'SUCCEEDED' ? 'VALID' : undefined,
      dependencies: [],
      inputFingerprint: snapshot.inputFingerprint,
      attemptCount: 0,
      createdAt: snapshot.updatedAt,
      updatedAt: snapshot.updatedAt,
      endedAt: executionStatus === 'SUCCEEDED' || executionStatus === 'FAILED' ? snapshot.updatedAt : undefined,
      migratedFromLegacy: true
    },
    legacyOutput: snapshot.output
  }
}

/**
 * Reuse is an identity decision, not a timestamp decision.
 * INSUFFICIENT is reusable when the exact inputs are unchanged because "no more evidence" is itself a valid result.
 */
export function isReusableTaskResult(task: TaskRecord, expectedInputFingerprint: string): boolean {
  return (
    task.executionStatus === 'SUCCEEDED' &&
    (task.resultStatus === 'VALID' || task.resultStatus === 'INSUFFICIENT') &&
    Boolean(task.inputFingerprint) &&
    task.inputFingerprint === expectedInputFingerprint
  )
}

/** Preserve the completed execution/output identity while marking its business result stale. */
export function invalidateTaskResult(
  task: TaskRecord,
  reason: string,
  invalidatedAt: string,
  invalidatedBy?: string
): TaskRecord {
  if (task.executionStatus !== 'SUCCEEDED') return task
  return {
    ...task,
    resultStatus: 'STALE',
    invalidation: { reason, invalidatedBy, invalidatedAt },
    updatedAt: invalidatedAt
  }
}

export function dependenciesMatch(
  task: TaskRecord,
  currentFingerprints: Readonly<Record<string, string | undefined>>
): boolean {
  return task.dependencies.every((dependency) =>
    currentFingerprints[dependency.taskId] === dependency.resultFingerprint
  )
}
