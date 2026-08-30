from pathlib import Path

# 1) Add deterministic journal projection helper.
task_model = Path('product-operation-report-app/src/shared/taskModel.ts')
text = task_model.read_text(encoding='utf-8')
anchor = "export function isReusableTaskResult(task: TaskRecord, expectedInputFingerprint: string): boolean {"
helper = """export function projectLegacyTaskJournal(\n  journal: Readonly<Record<string, ProjectTaskSnapshot>>\n): Record<string, TaskRecord> {\n  return Object.fromEntries(\n    Object.entries(journal).map(([taskId, snapshot]) => [taskId, projectLegacyTaskSnapshot(taskId, snapshot).task])\n  )\n}\n\n"""
if helper.strip() not in text:
    if text.count(anchor) != 1:
        raise SystemExit('taskModel.ts reuse anchor mismatch')
    text = text.replace(anchor, helper + anchor)
task_model.write_text(text, encoding='utf-8')

# 2) Add derived taskRecords to SavedProject while legacy taskJournal remains runtime authority in Phase 1A.
types = Path('product-operation-report-app/src/shared/types.ts')
text = types.read_text(encoding='utf-8')
old = "  /** Incremental checkpoints used to resume only unfinished model batches after a crash. */\n  taskJournal?: Record<string, ProjectTaskSnapshot>\n  reportMarkdown: string"
new = "  /** Incremental checkpoints used by the current production runtime. */\n  taskJournal?: Record<string, ProjectTaskSnapshot>\n  /** Phase 1A deterministic projection of taskJournal into the canonical task domain model. */\n  taskRecords?: Record<string, import('./taskModel').TaskRecord>\n  reportMarkdown: string"
if text.count(old) != 1:
    raise SystemExit('types.ts taskJournal anchor mismatch')
text = text.replace(old, new)
types.write_text(text, encoding='utf-8')

# 3) Project sanitized legacy journal into taskRecords at the persistence boundary.
project = Path('product-operation-report-app/src/main/project.ts')
text = project.read_text(encoding='utf-8')
import_anchor = "} from '../shared/types'\n"
import_line = "import { projectLegacyTaskJournal } from '../shared/taskModel'\n"
if import_line not in text:
    if text.count(import_anchor) != 1:
        raise SystemExit('project.ts import anchor mismatch')
    text = text.replace(import_anchor, import_anchor + import_line)
start_old = "function sanitizeProject(value: unknown): SavedProject {\n  const input = isPlainObject(value) ? value : {}\n  return {"
start_new = "function sanitizeProject(value: unknown): SavedProject {\n  const input = isPlainObject(value) ? value : {}\n  const taskJournal = sanitizeTaskJournal(input.taskJournal)\n  return {"
if text.count(start_old) != 1:
    raise SystemExit('project.ts sanitizeProject start mismatch')
text = text.replace(start_old, start_new)
field_old = "    taskJournal: sanitizeTaskJournal(input.taskJournal),\n    reportMarkdown: asString(input.reportMarkdown),"
field_new = "    taskJournal,\n    taskRecords: projectLegacyTaskJournal(taskJournal),\n    reportMarkdown: asString(input.reportMarkdown),"
if text.count(field_old) != 1:
    raise SystemExit('project.ts taskJournal field mismatch')
text = text.replace(field_old, field_new)
project.write_text(text, encoding='utf-8')

# 4) Extend pure task-model tests for whole-journal projection.
test = Path('product-operation-report-app/src/shared/taskModel.test.ts')
text = test.read_text(encoding='utf-8')
import_old = "  projectLegacyTaskSnapshot,\n  type TaskRecord"
import_new = "  projectLegacyTaskJournal,\n  projectLegacyTaskSnapshot,\n  type TaskRecord"
if text.count(import_old) != 1:
    raise SystemExit('taskModel.test.ts import anchor mismatch')
text = text.replace(import_old, import_new)
marker = "  it('projects legacy task journal records deterministically without rewriting inline output', () => {"
new_test = """  it('projects a sanitized legacy journal into canonical task records without carrying large outputs', () => {\n    const journal: Record<string, ProjectTaskSnapshot> = {\n      'clean:source-a': {\n        kind: 'source_clean',\n        status: 'complete',\n        output: '大段旧清洗结果不应复制进TaskRecord',\n        inputFingerprint: 'clean-input',\n        updatedAt: '2026-08-20T02:00:00.000Z'\n      },\n      'module:m5': {\n        kind: 'module',\n        status: 'interrupted',\n        updatedAt: '2026-08-20T02:01:00.000Z'\n      }\n    }\n    const projected = projectLegacyTaskJournal(journal)\n    expect(projected['clean:source-a']).toMatchObject({\n      kind: 'SOURCE_CLEAN',\n      executionStatus: 'SUCCEEDED',\n      resultStatus: 'VALID',\n      inputFingerprint: 'clean-input',\n      migratedFromLegacy: true\n    })\n    expect(projected['module:m5'].executionStatus).toBe('PAUSED')\n    expect('legacyOutput' in projected['clean:source-a']).toBe(false)\n  })\n\n"""
if new_test.strip() not in text:
    if text.count(marker) != 1:
        raise SystemExit('taskModel.test.ts insertion marker mismatch')
    text = text.replace(marker, new_test + marker)
test.write_text(text, encoding='utf-8')
