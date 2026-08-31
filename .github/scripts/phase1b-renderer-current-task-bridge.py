from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new)

store = Path('product-operation-report-app/src/renderer/src/store.ts')
text = store.read_text(encoding='utf-8')

text = replace_once(
    text,
    "import { reconcileTaskRecordMirror, type TaskRecord } from '../../shared/taskModel'\n",
    "import { sanitizeTaskCurrentIndex, type TaskCurrentIndex } from '../../shared/taskCurrentIndex'\nimport { reconcileTaskRecordMirror, type TaskRecord } from '../../shared/taskModel'\n",
    'current task index import'
)

text = replace_once(
    text,
    """  taskJournal: Record<string, ProjectTaskSnapshot>
  taskRecords: Record<string, TaskRecord>
  reportMarkdown: string
""",
    """  taskJournal: Record<string, ProjectTaskSnapshot>
  taskRecords: Record<string, TaskRecord>
  currentTaskByLogicalKey: TaskCurrentIndex
  reportMarkdown: string
""",
    'store state current task field'
)

text = replace_once(
    text,
    """  'cleanedData' | 'phase' | 'abortFn' | 'exportStatus' | 'cleaningProgress' | 'reportReuseOffer' | 'taskJournal' | 'taskRecords' | 'moduleStates'
""",
    """  'cleanedData' | 'phase' | 'abortFn' | 'exportStatus' | 'cleaningProgress' | 'reportReuseOffer' | 'taskJournal' | 'taskRecords' | 'currentTaskByLogicalKey' | 'moduleStates'
""",
    'invalidated analysis current task pick'
)

text = replace_once(
    text,
    """  taskJournal: {},
  taskRecords: {},
  moduleStates: {}
})
""",
    """  taskJournal: {},
  taskRecords: {},
  currentTaskByLogicalKey: {},
  moduleStates: {}
})
""",
    'invalidated analysis current task reset'
)

text = replace_once(
    text,
    """  taskJournal: {},
  taskRecords: {},
  reportMarkdown: '',
""",
    """  taskJournal: {},
  taskRecords: {},
  currentTaskByLogicalKey: {},
  reportMarkdown: '',
""",
    'initial current task state'
)

text = replace_once(
    text,
    """    const restoredTaskRecords = reconcileTaskRecordMirror(restoredTaskJournal, lastProject?.taskRecords || {})
    set({
""",
    """    const restoredTaskRecords = reconcileTaskRecordMirror(restoredTaskJournal, lastProject?.taskRecords || {})
    const restoredCurrentTaskByLogicalKey = sanitizeTaskCurrentIndex(
      lastProject?.currentTaskByLogicalKey,
      restoredTaskRecords
    )
    set({
""",
    'initial restore current task sanitize'
)

text = replace_once(
    text,
    """      taskJournal: restoredTaskJournal,
      taskRecords: restoredTaskRecords,
      reportMarkdown: restoredReport,
""",
    """      taskJournal: restoredTaskJournal,
      taskRecords: restoredTaskRecords,
      currentTaskByLogicalKey: restoredCurrentTaskByLogicalKey,
      reportMarkdown: restoredReport,
""",
    'initial restore current task state'
)

text = replace_once(
    text,
    """      taskJournal: current.taskJournal,
      taskRecords: current.taskRecords,
      reportMarkdown: current.reportMarkdown,
""",
    """      taskJournal: current.taskJournal,
      taskRecords: current.taskRecords,
      currentTaskByLogicalKey: current.currentTaskByLogicalKey,
      reportMarkdown: current.reportMarkdown,
""",
    'reset rollback current task state'
)

text = replace_once(
    text,
    """      taskJournal: {} as Record<string, ProjectTaskSnapshot>,
      taskRecords: {} as Record<string, TaskRecord>,
      reportMarkdown: '',
""",
    """      taskJournal: {} as Record<string, ProjectTaskSnapshot>,
      taskRecords: {} as Record<string, TaskRecord>,
      currentTaskByLogicalKey: {} as TaskCurrentIndex,
      reportMarkdown: '',
""",
    'new analysis current task reset'
)

text = replace_once(
    text,
    """    const restoredPreviousTaskJournal = previous.taskJournal || {}
    const restoredPreviousTaskRecords = reconcileTaskRecordMirror(restoredPreviousTaskJournal, previous.taskRecords || {})

    const restoredState = {
""",
    """    const restoredPreviousTaskJournal = previous.taskJournal || {}
    const restoredPreviousTaskRecords = reconcileTaskRecordMirror(restoredPreviousTaskJournal, previous.taskRecords || {})
    const restoredPreviousCurrentTaskByLogicalKey = sanitizeTaskCurrentIndex(
      previous.currentTaskByLogicalKey,
      restoredPreviousTaskRecords
    )

    const restoredState = {
""",
    'previous restore current task sanitize'
)

text = replace_once(
    text,
    """      taskJournal: restoredPreviousTaskJournal,
      taskRecords: restoredPreviousTaskRecords,
      reportMarkdown: restoredReport,
""",
    """      taskJournal: restoredPreviousTaskJournal,
      taskRecords: restoredPreviousTaskRecords,
      currentTaskByLogicalKey: restoredPreviousCurrentTaskByLogicalKey,
      reportMarkdown: restoredReport,
""",
    'previous restore current task state'
)

store.write_text(text, encoding='utf-8')
