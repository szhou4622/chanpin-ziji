from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new)

# Fix the strict task-record sanitizer's numeric narrowing.
task_model = Path('product-operation-report-app/src/shared/taskModel.ts')
text = task_model.read_text(encoding='utf-8')
text = replace_once(
    text,
    "    if (!Number.isSafeInteger(raw.attemptCount) || Number(raw.attemptCount) < 0 || Number(raw.attemptCount) > 10_000) continue\n",
    "    if (typeof raw.attemptCount !== 'number' || !Number.isSafeInteger(raw.attemptCount) || raw.attemptCount < 0 || raw.attemptCount > 10_000) continue\n",
    'taskModel attemptCount narrowing'
)
task_model.write_text(text, encoding='utf-8')

# Main-process persistence: trust canonical metadata only after strict sanitization,
# and only when it corresponds to the exact same journal mutation.
project = Path('product-operation-report-app/src/main/project.ts')
text = project.read_text(encoding='utf-8')
text = replace_once(
    text,
    "import { projectLegacyTaskJournal } from '../shared/taskModel'\n",
    "import { reconcileTaskRecordMirror, sanitizeTaskRecords } from '../shared/taskModel'\n",
    'project task model import'
)
text = replace_once(
    text,
    "  const taskJournal = sanitizeTaskJournal(input.taskJournal)\n  return {\n",
    "  const taskJournal = sanitizeTaskJournal(input.taskJournal)\n  const taskRecords = reconcileTaskRecordMirror(taskJournal, sanitizeTaskRecords(input.taskRecords))\n  return {\n",
    'project reconcile setup'
)
text = replace_once(
    text,
    "    taskJournal,\n    taskRecords: projectLegacyTaskJournal(taskJournal),\n",
    "    taskJournal,\n    taskRecords,\n",
    'project task records output'
)
project.write_text(text, encoding='utf-8')

# Renderer store: keep taskJournal as read authority while shadow-writing canonical taskRecords.
store = Path('product-operation-report-app/src/renderer/src/store.ts')
text = store.read_text(encoding='utf-8')
text = replace_once(
    text,
    "import { REPORT_MODULES, REPORT_MODULES_V2, SOP_STEPS } from '../../shared/types'\n",
    "import { REPORT_MODULES, REPORT_MODULES_V2, SOP_STEPS } from '../../shared/types'\nimport { reconcileTaskRecordMirror, type TaskRecord } from '../../shared/taskModel'\n",
    'store task model import'
)
text = replace_once(
    text,
    "import { removeTaskJournalEntries, writeTaskJournalEntry } from './store/taskJournalAdapter'\n",
    "import { removeRuntimeTaskState, writeRuntimeTaskState } from './store/taskJournalAdapter'\n",
    'store adapter import'
)
text = replace_once(
    text,
    "  taskJournal: Record<string, ProjectTaskSnapshot>\n  reportMarkdown: string\n",
    "  taskJournal: Record<string, ProjectTaskSnapshot>\n  taskRecords: Record<string, TaskRecord>\n  reportMarkdown: string\n",
    'store state taskRecords'
)
text = replace_once(
    text,
    "  'cleanedData' | 'phase' | 'abortFn' | 'exportStatus' | 'cleaningProgress' | 'reportReuseOffer' | 'taskJournal' | 'moduleStates'\n",
    "  'cleanedData' | 'phase' | 'abortFn' | 'exportStatus' | 'cleaningProgress' | 'reportReuseOffer' | 'taskJournal' | 'taskRecords' | 'moduleStates'\n",
    'invalidated pick taskRecords'
)
text = replace_once(
    text,
    "  reportReuseOffer: null,\n  taskJournal: {},\n  moduleStates: {}\n",
    "  reportReuseOffer: null,\n  taskJournal: {},\n  taskRecords: {},\n  moduleStates: {}\n",
    'invalidated taskRecords reset'
)
text = replace_once(
    text,
    "  artifacts: {},\n  taskJournal: {},\n  reportMarkdown: '',\n",
    "  artifacts: {},\n  taskJournal: {},\n  taskRecords: {},\n  reportMarkdown: '',\n",
    'initial taskRecords'
)

# Reconcile after all load-time journal corrections have run, so repaired/deleted journal
# entries cannot keep stale canonical metadata.
text = replace_once(
    text,
    "    const restoredCleanDetails = groupLegacyOfficeCleanDetails(\n      Array.isArray(lastProject?.cleanDetails) ? lastProject.cleanDetails : [],\n      restoredSourceState.derivedParentIds,\n      restoredSourceState.sources\n    )\n    set({\n",
    "    const restoredCleanDetails = groupLegacyOfficeCleanDetails(\n      Array.isArray(lastProject?.cleanDetails) ? lastProject.cleanDetails : [],\n      restoredSourceState.derivedParentIds,\n      restoredSourceState.sources\n    )\n    const restoredTaskRecords = reconcileTaskRecordMirror(restoredTaskJournal, lastProject?.taskRecords || {})\n    set({\n",
    'init reconciled taskRecords'
)
text = replace_once(
    text,
    "      artifacts: restoredArtifacts,\n      taskJournal: restoredTaskJournal,\n      reportMarkdown: restoredReport,\n",
    "      artifacts: restoredArtifacts,\n      taskJournal: restoredTaskJournal,\n      taskRecords: restoredTaskRecords,\n      reportMarkdown: restoredReport,\n",
    'init assign taskRecords'
)
text = replace_once(
    text,
    "      artifacts: current.artifacts,\n      taskJournal: current.taskJournal,\n      reportMarkdown: current.reportMarkdown,\n",
    "      artifacts: current.artifacts,\n      taskJournal: current.taskJournal,\n      taskRecords: current.taskRecords,\n      reportMarkdown: current.reportMarkdown,\n",
    'reset previous taskRecords'
)
text = replace_once(
    text,
    "      artifacts: {} as Record<number, string>,\n      taskJournal: {} as Record<string, ProjectTaskSnapshot>,\n      reportMarkdown: '',\n",
    "      artifacts: {} as Record<number, string>,\n      taskJournal: {} as Record<string, ProjectTaskSnapshot>,\n      taskRecords: {} as Record<string, TaskRecord>,\n      reportMarkdown: '',\n",
    'reset empty taskRecords'
)
text = replace_once(
    text,
    "    const restoredState = {\n",
    "    const restoredPreviousTaskJournal = previous.taskJournal || {}\n    const restoredPreviousTaskRecords = reconcileTaskRecordMirror(restoredPreviousTaskJournal, previous.taskRecords || {})\n\n    const restoredState = {\n",
    'restore previous reconcile setup'
)
text = replace_once(
    text,
    "      artifacts: restoredArtifacts,\n      taskJournal: previous.taskJournal || {},\n      reportMarkdown: restoredReport,\n",
    "      artifacts: restoredArtifacts,\n      taskJournal: restoredPreviousTaskJournal,\n      taskRecords: restoredPreviousTaskRecords,\n      reportMarkdown: restoredReport,\n",
    'restore previous assign taskRecords'
)

# Runtime dual writes.
text = replace_once(
    text,
    """                set((state) => ({
                  taskJournal: writeTaskJournalEntry(state.taskJournal, batchTaskId, {
                    kind: 'source_clean',
                    status: 'complete',
                    output: verifiedText
                  }),
                  cleaningProgress: {
""",
    """                set((state) => ({
                  ...writeRuntimeTaskState(state.taskJournal, state.taskRecords, batchTaskId, {
                    kind: 'source_clean',
                    status: 'complete',
                    output: verifiedText,
                    resultStatus: 'VALID',
                    sourceId: s.id
                  }),
                  cleaningProgress: {
""",
    'clean batch dual write'
)
text = replace_once(
    text,
    """        set((state) => ({
          taskJournal: writeTaskJournalEntry(state.taskJournal, savedTaskId, {
            kind: 'module', status: 'failed', output: result.text, inputFingerprint
          })
        }))
""",
    """        set((state) => ({
          ...writeRuntimeTaskState(state.taskJournal, state.taskRecords, savedTaskId, {
            kind: 'module', status: 'failed', output: result.text, inputFingerprint, moduleKey: module.key
          })
        }))
""",
    'module request failure dual write'
)
text = replace_once(
    text,
    """        set((state) => ({
          taskJournal: writeTaskJournalEntry(state.taskJournal, savedTaskId, {
            kind: 'module', status: 'failed', output: moduleOutput, inputFingerprint
          })
        }))
""",
    """        set((state) => ({
          ...writeRuntimeTaskState(state.taskJournal, state.taskRecords, savedTaskId, {
            kind: 'module', status: 'failed', output: moduleOutput, inputFingerprint, moduleKey: module.key
          })
        }))
""",
    'module validation failure dual write'
)
text = replace_once(
    text,
    """        set((state) => ({
          taskJournal: writeTaskJournalEntry(state.taskJournal, savedTaskId, {
            kind: 'module', status: 'complete', output, inputFingerprint
          })
        }))
""",
    """        set((state) => ({
          ...writeRuntimeTaskState(state.taskJournal, state.taskRecords, savedTaskId, {
            kind: 'module', status: 'complete', output, inputFingerprint,
            resultStatus: 'INSUFFICIENT', moduleKey: module.key
          })
        }))
""",
    'module insufficient dual write'
)
text = replace_once(
    text,
    """      set((state) => ({
        artifacts: { ...state.artifacts, [module.id]: moduleOutput },
        taskJournal: writeTaskJournalEntry(state.taskJournal, savedTaskId, {
          kind: 'module', status: 'complete', output: moduleOutput, inputFingerprint
        })
      }))
""",
    """      set((state) => ({
        artifacts: { ...state.artifacts, [module.id]: moduleOutput },
        ...writeRuntimeTaskState(state.taskJournal, state.taskRecords, savedTaskId, {
          kind: 'module', status: 'complete', output: moduleOutput, inputFingerprint,
          resultStatus: 'VALID', moduleKey: module.key
        })
      }))
""",
    'module valid dual write'
)
text = replace_once(
    text,
    """        set((state) => ({
          taskJournal: writeTaskJournalEntry(state.taskJournal, taskId, {
            kind: 'module', status: 'failed'
          })
        }))
""",
    """        set((state) => ({
          ...writeRuntimeTaskState(state.taskJournal, state.taskRecords, taskId, {
            kind: 'module', status: 'failed', moduleKey: module.key
          })
        }))
""",
    'wave rejection dual write'
)
text = replace_once(
    text,
    """      taskJournal: removeTaskJournalEntries(
        state.taskJournal,
        (taskId) => [...affected].some((moduleKey) => taskId.includes(`:module:v2:${moduleKey}`))
      ),
""",
    """      ...removeRuntimeTaskState(
        state.taskJournal,
        state.taskRecords,
        (taskId) => [...affected].some((moduleKey) => taskId.includes(`:module:v2:${moduleKey}`))
      ),
""",
    'retry removes both task representations'
)
store.write_text(text, encoding='utf-8')
