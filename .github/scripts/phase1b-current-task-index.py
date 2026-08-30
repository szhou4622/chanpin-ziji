from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new)

# SavedProject persistence contract.
types = Path('product-operation-report-app/src/shared/types.ts')
text = types.read_text(encoding='utf-8')
text = replace_once(
    text,
    """  /** Phase 1A deterministic projection of taskJournal into the canonical task domain model. */
  taskRecords?: Record<string, import('./taskModel').TaskRecord>
  reportMarkdown: string
""",
    """  /** Phase 1A deterministic projection of taskJournal into the canonical task domain model. */
  taskRecords?: Record<string, import('./taskModel').TaskRecord>
  /** Explicit current Task instance pointer per stable logical business slot. */
  currentTaskByLogicalKey?: import('./taskCurrentIndex').TaskCurrentIndex
  reportMarkdown: string
""",
    'SavedProject current task index'
)
types.write_text(text, encoding='utf-8')

# Main-process sanitizer: validate pointers only after canonical task records are sanitized/reconciled.
project = Path('product-operation-report-app/src/main/project.ts')
text = project.read_text(encoding='utf-8')
text = replace_once(
    text,
    "import { reconcileTaskRecordMirror, sanitizeTaskRecords } from '../shared/taskModel'\n",
    "import { reconcileTaskRecordMirror, sanitizeTaskRecords } from '../shared/taskModel'\nimport { sanitizeTaskCurrentIndex } from '../shared/taskCurrentIndex'\n",
    'project current index import'
)
text = replace_once(
    text,
    """  const taskJournal = sanitizeTaskJournal(input.taskJournal)
  const taskRecords = reconcileTaskRecordMirror(taskJournal, sanitizeTaskRecords(input.taskRecords))
  return {
""",
    """  const taskJournal = sanitizeTaskJournal(input.taskJournal)
  const taskRecords = reconcileTaskRecordMirror(taskJournal, sanitizeTaskRecords(input.taskRecords))
  const currentTaskByLogicalKey = sanitizeTaskCurrentIndex(input.currentTaskByLogicalKey, taskRecords)
  return {
""",
    'project current index sanitize'
)
text = replace_once(
    text,
    """    taskJournal,
    taskRecords,
    reportMarkdown: asString(input.reportMarkdown),
""",
    """    taskJournal,
    taskRecords,
    currentTaskByLogicalKey,
    reportMarkdown: asString(input.reportMarkdown),
""",
    'project current index output'
)
project.write_text(text, encoding='utf-8')
