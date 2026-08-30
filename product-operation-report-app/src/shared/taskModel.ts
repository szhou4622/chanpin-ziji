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

const TASK_ID_PATTERN = /^[\w.:@/+-]{1,300}$/u
const MODULE_KEYS = new Set<ModuleKey>([
  'product-info',
  'platform-audience',
  'material-review',
  'benchmark-brands',
  'selling-points',
  'voc',
  'selling-point-ranking',
  'audience-sp-scene'
])
const EXECUTION_STATUS_SET = new Set<string>(TASK_EXECUTION_STATUSES)
const RESULT_STATUS_SET = new Set<string>(TASK_RESULT_STATUSES)
const TASK_KIND_SET = new Set<string>(TASK_KINDS)

type PlainRecord = Record<string, unknown>

function isPlainObject(value: unknown): value is PlainRecord {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function validDate(value: unknown): value is string {
  return typeof value === 'string' && Number.isFinite(Date.parse(value))
}

function boundedString(value: unknown, max: number): string | undefined {
  return typeof value === 'string' && value.length > 0 && value.length <= max ? value : undefined
}

function optionalDate(value: unknown): string | undefined | null {
  if (value === undefined) return undefined
  return validDate(value) ? value : null
}

function sanitizeDependencies(value: unknown): TaskDependencySnapshot[] | null {
  if (!Array.isArray(value) || value.length > 64) return null
  const result: TaskDependencySnapshot[] = []
  const seen = new Set<string>()
  for (const item of value) {
    if (!isPlainObject(item)) return null
    const taskId = boundedString(item.taskId, 300)
    const resultFingerprint = boundedString(item.resultFingerprint, 2_000)
    if (!taskId || !TASK_ID_PATTERN.test(taskId) || !resultFingerprint || seen.has(taskId)) return null
    seen.add(taskId)
    result.push({ taskId, resultFingerprint })
  }
  return result
}

function sanitizeInvalidation(value: unknown): TaskInvalidation | undefined | null {
  if (value === undefined) return undefined
  if (!isPlainObject(value)) return null
  const reason = boundedString(value.reason, 1_000)
  const invalidatedAt = validDate(value.invalidatedAt) ? value.invalidatedAt : undefined
  const invalidatedBy = value.invalidatedBy === undefined ? undefined : boundedString(value.invalidatedBy, 300)
  if (!reason || !invalidatedAt || (value.invalidatedBy !== undefined && !invalidatedBy)) return null
  return { reason, invalidatedAt, invalidatedBy }
}

/**
 * Strictly validates persisted canonical task metadata. Invalid records are dropped
 * so a corrupt or hand-edited project cannot become authoritative task state.
 */
export function sanitizeTaskRecords(value: unknown): Record<string, TaskRecord> {
  if (!isPlainObject(value)) return {}
  const result: Record<string, TaskRecord> = {}
  for (const [taskId, raw] of Object.entries(value)) {
    if (!TASK_ID_PATTERN.test(taskId) || !isPlainObject(raw)) continue
    if (raw.schemaVersion !== 1 || raw.id !== taskId) continue
    if (typeof raw.kind !== 'string' || !TASK_KIND_SET.has(raw.kind)) continue
    if (typeof raw.executionStatus !== 'string' || !EXECUTION_STATUS_SET.has(raw.executionStatus)) continue
    const executionStatus = raw.executionStatus as TaskExecutionStatus
    const resultStatus = raw.resultStatus === undefined
      ? undefined
      : typeof raw.resultStatus === 'string' && RESULT_STATUS_SET.has(raw.resultStatus)
        ? raw.resultStatus as TaskResultStatus
        : null
    if (resultStatus === null) continue
    if (executionStatus === 'SUCCEEDED' ? !resultStatus : Boolean(resultStatus)) continue
    const dependencies = sanitizeDependencies(raw.dependencies)
    if (!dependencies) continue
    if (typeof raw.attemptCount !== 'number' || !Number.isSafeInteger(raw.attemptCount) || raw.attemptCount < 0 || raw.attemptCount > 10_000) continue
    if (!validDate(raw.createdAt) || !validDate(raw.updatedAt)) continue
    const startedAt = optionalDate(raw.startedAt)
    const endedAt = optionalDate(raw.endedAt)
    const retryAt = optionalDate(raw.retryAt)
    if (startedAt === null || endedAt === null || retryAt === null) continue
    const inputFingerprint = raw.inputFingerprint === undefined ? undefined : boundedString(raw.inputFingerprint, 2_000)
    const resultFingerprint = raw.resultFingerprint === undefined ? undefined : boundedString(raw.resultFingerprint, 2_000)
    const sourceId = raw.sourceId === undefined ? undefined : boundedString(raw.sourceId, 300)
    const errorClass = raw.errorClass === undefined ? undefined : boundedString(raw.errorClass, 200)
    const outputRef = raw.outputRef === undefined ? undefined : boundedString(raw.outputRef, 1_000)
    if (
      (raw.inputFingerprint !== undefined && !inputFingerprint) ||
      (raw.resultFingerprint !== undefined && !resultFingerprint) ||
      (raw.sourceId !== undefined && !sourceId) ||
      (raw.errorClass !== undefined && !errorClass) ||
      (raw.outputRef !== undefined && !outputRef)
    ) continue
    const moduleKey = raw.moduleKey === undefined
      ? undefined
      : typeof raw.moduleKey === 'string' && MODULE_KEYS.has(raw.moduleKey as ModuleKey)
        ? raw.moduleKey as ModuleKey
        : null
    if (moduleKey === null) continue
    const invalidation = sanitizeInvalidation(raw.invalidation)
    if (invalidation === null) continue
    if (raw.migratedFromLegacy !== undefined && typeof raw.migratedFromLegacy !== 'boolean') continue
    result[taskId] = {
      schemaVersion: 1,
      id: taskId,
      kind: raw.kind as TaskKind,
      executionStatus,
      resultStatus,
      dependencies,
      inputFingerprint,
      resultFingerprint,
      sourceId,
      moduleKey,
      attemptCount: Number(raw.attemptCount),
      errorClass,
      retryAt,
      outputRef,
      invalidation,
      createdAt: raw.createdAt,
      updatedAt: raw.updatedAt,
      startedAt,
      endedAt,
      migratedFromLegacy: raw.migratedFromLegacy as boolean | undefined
    }
  }
  return result
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

export function projectLegacyTaskJournal(
  journal: Readonly<Record<string, ProjectTaskSnapshot>>
): Record<string, TaskRecord> {
  return Object.fromEntries(
    Object.entries(journal).map(([taskId, snapshot]) => [taskId, projectLegacyTaskSnapshot(taskId, snapshot).task])
  )
}

/**
 * During the dual-write bridge the journal remains the read authority. Persisted
 * canonical records are accepted only for journal tasks with the exact same
 * updatedAt, proving both sides came from the same logical mutation.
 */
export function reconcileTaskRecordMirror(
  journal: Readonly<Record<string, ProjectTaskSnapshot>>,
  persisted: Readonly<Record<string, TaskRecord>>
): Record<string, TaskRecord> {
  const projected = projectLegacyTaskJournal(journal)
  for (const [taskId, snapshot] of Object.entries(journal)) {
    const canonical = persisted[taskId]
    if (canonical && canonical.id === taskId && canonical.updatedAt === snapshot.updatedAt) {
      projected[taskId] = canonical
    }
  }
  return projected
}

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
