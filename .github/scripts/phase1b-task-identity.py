from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new)

model = Path('product-operation-report-app/src/shared/taskModel.ts')
text = model.read_text(encoding='utf-8')
text = replace_once(
    text,
    "import type { ModuleKey, ProjectTaskSnapshot } from './types'\n",
    "import { isValidTaskIdentityKey } from './taskIdentity'\nimport type { ModuleKey, ProjectTaskSnapshot } from './types'\n",
    'identity import'
)
text = replace_once(
    text,
    """export interface TaskRecord {
  schemaVersion: 1
  id: string
  kind: TaskKind
""",
    """export interface TaskRecord {
  schemaVersion: 1
  /** Immutable id of this logical-task instance. */
  id: string
  /** Stable business slot shared by replacement task instances. */
  logicalKey?: string
  /** Transitional key of the legacy payload carrier while journal output still exists. */
  payloadKey?: string
  kind: TaskKind
""",
    'task identity fields'
)
text = replace_once(text, "const TASK_ID_PATTERN = /^[\\w.:@/+-]{1,300}$/u\n", '', 'remove duplicated id pattern')
text = text.replace('!TASK_ID_PATTERN.test(taskId)', '!isValidTaskIdentityKey(taskId)')
text = text.replace('!TASK_ID_PATTERN.test(key)', '!isValidTaskIdentityKey(key)')

old_fields = """    const inputFingerprint = raw.inputFingerprint === undefined ? undefined : boundedString(raw.inputFingerprint, 2_000)
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
"""
new_fields = """    const inputFingerprint = raw.inputFingerprint === undefined ? undefined : boundedString(raw.inputFingerprint, 2_000)
    const resultFingerprint = raw.resultFingerprint === undefined ? undefined : boundedString(raw.resultFingerprint, 2_000)
    const sourceId = raw.sourceId === undefined ? undefined : boundedString(raw.sourceId, 300)
    const logicalKey = raw.logicalKey === undefined ? undefined : boundedString(raw.logicalKey, 300)
    const payloadKey = raw.payloadKey === undefined ? undefined : boundedString(raw.payloadKey, 300)
    const errorClass = raw.errorClass === undefined ? undefined : boundedString(raw.errorClass, 200)
    const outputRef = raw.outputRef === undefined ? undefined : boundedString(raw.outputRef, 1_000)
    if (
      (raw.inputFingerprint !== undefined && !inputFingerprint) ||
      (raw.resultFingerprint !== undefined && !resultFingerprint) ||
      (raw.sourceId !== undefined && !sourceId) ||
      (raw.logicalKey !== undefined && (!logicalKey || !isValidTaskIdentityKey(logicalKey))) ||
      (raw.payloadKey !== undefined && (!payloadKey || !isValidTaskIdentityKey(payloadKey))) ||
      (raw.errorClass !== undefined && !errorClass) ||
      (raw.outputRef !== undefined && !outputRef)
    ) continue
"""
text = replace_once(text, old_fields, new_fields, 'sanitize identity fields')
text = replace_once(
    text,
    """      schemaVersion: 1,
      id: taskId,
      kind: raw.kind as TaskKind,
""",
    """      schemaVersion: 1,
      id: taskId,
      logicalKey,
      payloadKey,
      kind: raw.kind as TaskKind,
""",
    'sanitized task identity output'
)
text = replace_once(
    text,
    """      schemaVersion: 1,
      id: taskId,
      kind: LEGACY_KIND_MAP[snapshot.kind],
""",
    """      schemaVersion: 1,
      id: taskId,
      logicalKey: taskId,
      payloadKey: taskId,
      kind: LEGACY_KIND_MAP[snapshot.kind],
""",
    'legacy identity projection'
)
model.write_text(text, encoding='utf-8')

test = Path('product-operation-report-app/src/shared/taskModel.test.ts')
text = test.read_text(encoding='utf-8')
text = replace_once(
    text,
    """      id: 'session:module:v2:voc',
      resultStatus: 'INSUFFICIENT',
""",
    """      id: 'session:module:v2:voc@run-a',
      logicalKey: 'session:module:v2:voc',
      payloadKey: 'session:module:v2:voc',
      resultStatus: 'INSUFFICIENT',
""",
    'sanitizer valid identity'
)
text = replace_once(
    text,
    """      'bad:date': { ...valid, id: 'bad:date', updatedAt: 'not-a-date' },
      'bad:module': { ...valid, id: 'bad:module', moduleKey: 'made-up-module' }
""",
    """      'bad:date': { ...valid, id: 'bad:date', updatedAt: 'not-a-date' },
      'bad:module': { ...valid, id: 'bad:module', moduleKey: 'made-up-module' },
      'bad:logical': { ...valid, id: 'bad:logical', logicalKey: 'bad logical key' },
      'bad:payload': { ...valid, id: 'bad:payload', payloadKey: 'bad payload key' }
""",
    'sanitizer invalid identities'
)
text = replace_once(
    text,
    """      id: 'legacy:module:5',
      kind: 'MODULE_ANALYSIS',
""",
    """      id: 'legacy:module:5',
      logicalKey: 'legacy:module:5',
      payloadKey: 'legacy:module:5',
      kind: 'MODULE_ANALYSIS',
""",
    'legacy identity expectations'
)
test.write_text(text, encoding='utf-8')
