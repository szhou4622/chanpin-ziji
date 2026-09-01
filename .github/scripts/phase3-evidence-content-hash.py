from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new)

# Shared source types carry a full raw-content SHA-256 and stable source id into cleaning.
types_path = Path('product-operation-report-app/src/shared/types.ts')
types = types_path.read_text(encoding='utf-8')
types = replace_once(
    types,
    "export interface SourceCleanCacheInput {\n  name: string\n  kind: 'image' | 'doc' | 'table' | 'other'\n",
    "export interface SourceCleanCacheInput {\n  name: string\n  /** Stable project-local source identity; excluded from technical cache keys. */\n  sourceId?: string\n  /** Full SHA-256 of the exact top-level uploaded bytes; excluded from technical cache keys. */\n  contentHash?: string\n  kind: 'image' | 'doc' | 'table' | 'other'\n",
    'SourceCleanCacheInput identity fields',
)
types = replace_once(
    types,
    "  note?: string\n  size?: number\n  /** Root upload selected by the user. Derived pages/images/ZIP entries share this id. */\n",
    "  note?: string\n  size?: number\n  /** Full SHA-256 of the exact top-level uploaded bytes. */\n  contentHash?: string\n  /** Root upload selected by the user. Derived pages/images/ZIP entries share this id. */\n",
    'ProjectSourceSnapshot content hash',
)
types_path.write_text(types, encoding='utf-8')

# Renderer sources compute the digest once from bytes already loaded for parsing.
store_path = Path('product-operation-report-app/src/renderer/src/store.ts')
store = store_path.read_text(encoding='utf-8')
store = replace_once(
    store,
    "import { inferSourcePlatform } from './sourceMetadata'\nimport { buildModuleExecutionBatches } from './moduleDependencyResolver'\n",
    "import { inferSourcePlatform } from './sourceMetadata'\nimport { sha256ArrayBuffer } from './contentHash'\nimport { buildModuleExecutionBatches } from './moduleDependencyResolver'\n",
    'store content hash import',
)
store = replace_once(
    store,
    "  text?: string\n  size?: number\n  parsing?: boolean\n",
    "  text?: string\n  size?: number\n  contentHash?: string\n  parsing?: boolean\n",
    'renderer Source contentHash',
)
store = replace_once(
    store,
    "  return {\n    name: source.name,\n    kind: source.kind,\n",
    "  return {\n    name: source.name,\n    sourceId: source.id,\n    contentHash: source.contentHash,\n    kind: source.kind,\n",
    'cleaning input identity',
)
store = replace_once(
    store,
    "const downscaleImage = async (file: File, maxDim = 1600, quality = 0.9): Promise<string> => {\n  const headerBytes = new Uint8Array(await file.arrayBuffer())\n",
    "const downscaleImage = async (file: File, maxDim = 1600, quality = 0.9, sourceBytes?: ArrayBuffer): Promise<string> => {\n  const headerBytes = new Uint8Array(sourceBytes || await file.arrayBuffer())\n",
    'downscale accepts preloaded bytes',
)
store = replace_once(
    store,
    "          if (job.kind === 'image') {\n            const dataUrl = await downscaleImage(job.file)\n",
    "          if (job.kind === 'image') {\n            const buf = await job.file.arrayBuffer()\n            const contentHash = await sha256ArrayBuffer(buf)\n            const dataUrl = await downscaleImage(job.file, 1600, 0.9, buf)\n",
    'image raw hash',
)
store = replace_once(
    store,
    "a.id === job.id ? { ...a, parsing: false, dataUrl, error: undefined } : a",
    "a.id === job.id ? { ...a, parsing: false, dataUrl, contentHash, error: undefined } : a",
    'image source stores hash',
)
store = replace_once(
    store,
    "          if (job.ext === 'zip') {\n            const buf = await job.file.arrayBuffer()\n            const archiveItems = await window.api.parseArchive(job.name, buf)\n",
    "          if (job.ext === 'zip') {\n            const buf = await job.file.arrayBuffer()\n            const contentHash = await sha256ArrayBuffer(buf)\n            const archiveItems = await window.api.parseArchive(job.name, buf)\n",
    'archive raw hash',
)
store = replace_once(
    store,
    "                    note: `来自压缩包：${job.name}`,\n                    topLevelId: job.id,\n                    derivedKind: 'archive-entry' as const\n",
    "                    note: `来自压缩包：${job.name}`,\n                    contentHash,\n                    topLevelId: job.id,\n                    derivedKind: 'archive-entry' as const\n",
    'archive child inherits raw hash',
)
store = replace_once(
    store,
    "          const buf = await job.file.arrayBuffer()\n          const parsed = await window.api.parseFile(job.file.name, buf)\n",
    "          const buf = await job.file.arrayBuffer()\n          const contentHash = await sha256ArrayBuffer(buf)\n          const parsed = await window.api.parseFile(job.file.name, buf)\n",
    'document raw hash',
)
store = replace_once(
    store,
    "              kindV1: job.kindV1,\n              topLevelId: job.id\n            }\n",
    "              kindV1: job.kindV1,\n              contentHash,\n              topLevelId: job.id\n            }\n",
    'parsed parent stores hash',
)
store_path.write_text(store, encoding='utf-8')

# Project sanitization preserves only valid SHA-256 values; old projects remain hash-less.
project_path = Path('product-operation-report-app/src/main/project.ts')
project = project_path.read_text(encoding='utf-8')
project = replace_once(
    project,
    "import { reconcileTaskRecordMirror, sanitizeTaskRecords } from '../shared/taskModel'\nimport { sanitizeTaskCurrentIndex } from '../shared/taskCurrentIndex'\n",
    "import { reconcileTaskRecordMirror, sanitizeTaskRecords } from '../shared/taskModel'\nimport { sanitizeTaskCurrentIndex } from '../shared/taskCurrentIndex'\nimport { normalizeSha256 } from '../shared/evidenceIdentity'\n",
    'project evidence identity import',
)
project = replace_once(
    project,
    "    note: optionalString(value.note),\n    size: optionalNumber(value.size),\n    topLevelId: optionalString(value.topLevelId),\n",
    "    note: optionalString(value.note),\n    size: optionalNumber(value.size),\n    contentHash: normalizeSha256(value.contentHash),\n    topLevelId: optionalString(value.topLevelId),\n",
    'sanitize source hash',
)
project_path.write_text(project, encoding='utf-8')

# New sources use content-backed scopes; legacy projects keep the sampled 8-char scope.
batches_path = Path('product-operation-report-app/src/renderer/src/sourceCleanBatches.ts')
batches = batches_path.read_text(encoding='utf-8')
batches = replace_once(
    batches,
    "import { SOURCE_TEXT_LIMIT } from '../../shared/reportVersions'\n",
    "import { SOURCE_TEXT_LIMIT } from '../../shared/reportVersions'\nimport { evidenceScopeFromContentHash } from '../../shared/evidenceIdentity'\n",
    'source batch evidence import',
)
batches = replace_once(
    batches,
    "export function sourceEvidenceScope(source: SourceCleanCacheInput): string {\n  const content = source.text || source.dataUrl || ''\n",
    "export function sourceEvidenceScope(source: SourceCleanCacheInput): string {\n  const contentBacked = evidenceScopeFromContentHash(source.contentHash, source.sourceId)\n  if (contentBacked) return contentBacked\n  const content = source.text || source.dataUrl || ''\n",
    'content-backed evidence scope',
)
batches = replace_once(
    batches,
    "  // Evidence IDs only need to be compact and stable inside a report. Sampling the beginning,\n  // middle and end prevents same-name/same-prefix exports from sharing a scope without hashing\n  // hundreds of megabytes on the renderer thread.\n",
    "  // Legacy compatibility only: projects saved before contentHash existed keep their original\n  // 8-character sampled scope so existing cleaning ledgers and reports do not need migration.\n",
    'legacy scope comment',
)
batches_path.write_text(batches, encoding='utf-8')

# User-facing provenance replacement recognizes both legacy and content-backed IDs.
display_path = Path('product-operation-report-app/src/shared/reportDisplay.ts')
display = display_path.read_text(encoding='utf-8')
old_display_header = """const EVIDENCE_ID_ATOM = [
  '`{0,2}',
  '(?:',
  'POR-[RTI]-[A-F0-9]{8}-\\\\d{6}',
  '|POR-B-[A-F0-9]{8}-\\\\d{4}\\\\|ROWS:\\\\d+-\\\\d+\\\\|COUNT:\\\\d+',
  ')',
  '`{0,2}'
].join('')

const EVIDENCE_ID_SEQUENCE = new RegExp(
  `${EVIDENCE_ID_ATOM}(?:\\\\s*(?:[、,，；;]|和|及|/)\\\\s*${EVIDENCE_ID_ATOM})*`,
  'giu'
)

const EVIDENCE_ID_VALUE = /POR-[RTI]-[A-F0-9]{8}-\\d{6}|POR-B-[A-F0-9]{8}-\\d{4}\\|ROWS:\\d+-\\d+\\|COUNT:\\d+/giu
"""
new_display_header = """import { EVIDENCE_VALUE_PATTERN } from './evidenceIdentity'

const EVIDENCE_ID_ATOM = [
  '`{0,2}',
  `(?:${EVIDENCE_VALUE_PATTERN})`,
  '`{0,2}'
].join('')

const EVIDENCE_ID_SEQUENCE = new RegExp(
  `${EVIDENCE_ID_ATOM}(?:\\\\s*(?:[、,，；;]|和|及|/)\\\\s*${EVIDENCE_ID_ATOM})*`,
  'giu'
)

const EVIDENCE_ID_VALUE = new RegExp(EVIDENCE_VALUE_PATTERN, 'giu')
"""
display = replace_once(display, old_display_header, new_display_header, 'report display evidence patterns')
display_path.write_text(display, encoding='utf-8')

# Report evidence validation recognizes both formats without stateful global .test calls.
validate_path = Path('product-operation-report-app/src/renderer/src/validate.ts')
validate = validate_path.read_text(encoding='utf-8')
validate = replace_once(
    validate,
    "} from './reportTemplate'\n\n// 成稿前的来源绑定硬规则检查（启发式，非阻断，仅提示）\n",
    "} from './reportTemplate'\nimport { EVIDENCE_ID_PATTERN } from '../../shared/evidenceIdentity'\n\n// 成稿前的来源绑定硬规则检查（启发式，非阻断，仅提示）\n",
    'validate evidence pattern import',
)
validate = replace_once(
    validate,
    "  const idPattern = /\\bPOR-[RTI]-[A-F0-9]{8}-\\d{6}\\b/gu\n  const reportIds = [...new Set(md.match(idPattern) || [])]\n  const knownIds = new Set(cleanedData.match(idPattern) || [])\n",
    "  const idPattern = new RegExp(`\\\\b${EVIDENCE_ID_PATTERN}\\\\b`, 'gu')\n  const idLinePattern = new RegExp(`\\\\b${EVIDENCE_ID_PATTERN}\\\\b`, 'u')\n  const reportIds = [...new Set(md.match(idPattern) || [])]\n  const knownIds = new Set(cleanedData.match(idPattern) || [])\n",
    'validate evidence regex',
)
validate = replace_once(
    validate,
    "    if (!/\\d/u.test(trimmed) || /\\bPOR-[RTI]-[A-F0-9]{8}-\\d{6}\\b/u.test(trimmed)) return false\n",
    "    if (!/\\d/u.test(trimmed) || idLinePattern.test(trimmed)) return false\n",
    'validate evidence line regex',
)
validate_path.write_text(validate, encoding='utf-8')

# Regression tests: new format, duplicate-source separation, and legacy compatibility.
batch_test_path = Path('product-operation-report-app/src/renderer/src/sourceCleanBatches.test.ts')
batch_test = batch_test_path.read_text(encoding='utf-8')
batch_test = replace_once(
    batch_test,
    "  combineSourceCleanBatchOutputs,\n  sourceCleanBatchInternals\n",
    "  combineSourceCleanBatchOutputs,\n  sourceCleanBatchInternals,\n  sourceEvidenceScope\n",
    'batch test evidence import',
)
batch_test = replace_once(
    batch_test,
    "  it('accepts a CSV result with exactly one populated row per evidence ID', () => {\n",
    "  it('uses SHA-backed scopes for new sources while preserving the legacy fallback', () => {\n    const hash = 'ab'.repeat(32)\n    const scope = sourceEvidenceScope({ ...source, sourceId: '12345678-90ab-4def-8123-456789abcdef', contentHash: hash })\n    expect(scope).toBe('ABABABABABABABABABABABAB-1234567890AB')\n    expect(sourceEvidenceScope({ ...source, sourceId: 'fedcba98-7654-4321-8123-456789abcdef', contentHash: hash })).not.toBe(scope)\n    expect(sourceEvidenceScope(source)).toMatch(/^[A-F0-9]{8}$/u)\n  })\n\n  it('accepts a CSV result with exactly one populated row per evidence ID', () => {\n",
    'batch scope regression',
)
batch_test_path.write_text(batch_test, encoding='utf-8')

display_test_path = Path('product-operation-report-app/src/shared/reportDisplay.test.ts')
display_test = display_test_path.read_text(encoding='utf-8')
display_test = replace_once(
    display_test,
    "  it('also hides internal batch receipts if they leak into a report', () => {\n    expect(reportMarkdownForDisplay('依据 POR-B-ABCDEF12-0001|ROWS:1-50|COUNT:50'))\n      .toBe('依据 已核验资料')\n  })\n",
    "  it('also hides legacy and content-backed batch receipts if they leak into a report', () => {\n    expect(reportMarkdownForDisplay('依据 POR-B-ABCDEF12-0001|ROWS:1-50|COUNT:50'))\n      .toBe('依据 已核验资料')\n    expect(reportMarkdownForDisplay('依据 POR-B-ABABABABABABABABABABABAB-1234567890AB-0001|ROWS:1-50|COUNT:50'))\n      .toBe('依据 已核验资料')\n  })\n",
    'display receipt compatibility test',
)
display_test = replace_once(
    display_test,
    "    expect(reportMarkdownForDisplay('来源：POR-R-32F24FA0-000001', map))\n      .toBe('来源：经营数据表.xlsx')\n",
    "    expect(reportMarkdownForDisplay('来源：POR-R-32F24FA0-000001', map))\n      .toBe('来源：经营数据表.xlsx')\n\n    const contentMap = buildEvidenceSourceNameMap([{\n      name: '新版经营数据表.xlsx',\n      text: '__证据ID,成交金额\\nPOR-R-ABABABABABABABABABABABAB-1234567890AB-000001,211985.04'\n    }])\n    expect(reportMarkdownForDisplay('来源：POR-R-ABABABABABABABABABABABAB-1234567890AB-000001', contentMap))\n      .toBe('来源：新版经营数据表.xlsx')\n",
    'display content-backed id test',
)
display_test_path.write_text(display_test, encoding='utf-8')

validate_test_path = Path('product-operation-report-app/src/renderer/src/validate.test.ts')
validate_test = validate_test_path.read_text(encoding='utf-8')
validate_test = replace_once(
    validate_test,
    "import { validateReportStructure } from './validate'\n",
    "import { validateReportEvidenceLinks, validateReportStructure } from './validate'\n",
    'validate test import',
)
validate_test = replace_once(
    validate_test,
    "describe('six-module report structure', () => {\n",
    "describe('report evidence identity compatibility', () => {\n  it('accepts both legacy and SHA-backed evidence ids from the cleaning ledger', () => {\n    const legacy = 'POR-R-32F24FA0-000001'\n    const current = 'POR-T-ABABABABABABABABABABABAB-1234567890AB-000001'\n    const audit = validateReportEvidenceLinks(`金额 100，来源 ${legacy}；转化 20，来源 ${current}`, `${legacy}\\n${current}`)\n    expect(audit.errors).toEqual([])\n    expect(audit.linkedIds).toBe(2)\n  })\n})\n\ndescribe('six-module report structure', () => {\n",
    'validate evidence compatibility test',
)
validate_test_path.write_text(validate_test, encoding='utf-8')
