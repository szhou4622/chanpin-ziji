const EVIDENCE_ID_ATOM = [
  '`{0,2}',
  '(?:',
  'POR-[RTI]-[A-F0-9]{8}-\\d{6}',
  '|POR-B-[A-F0-9]{8}-\\d{4}\\|ROWS:\\d+-\\d+\\|COUNT:\\d+',
  ')',
  '`{0,2}'
].join('')

const EVIDENCE_ID_SEQUENCE = new RegExp(
  `${EVIDENCE_ID_ATOM}(?:\\s*(?:[、,，；;]|和|及|/)\\s*${EVIDENCE_ID_ATOM})*`,
  'giu'
)

const EVIDENCE_ID_VALUE = /POR-[RTI]-[A-F0-9]{8}-\d{6}|POR-B-[A-F0-9]{8}-\d{4}\|ROWS:\d+-\d+\|COUNT:\d+/giu

export type EvidenceSourceNameMap = Readonly<Record<string, string>>

const REPORT_MODULE_DECISION_NUMERALS = ['一', '二', '三', '四', '五', '六'] as const

export const REPORT_MODULE_DECISION_TITLES: Readonly<Record<number, string>> = {
  1: '产品信息',
  2: '成交人群分析',
  3: '内容素材判断',
  4: '卖点提炼与排序',
  5: '用户真实需求VOC',
  6: '人群×卖点×场景匹配'
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/gu, '\\$&')
}

function isCurrentSixModuleReport(markdown: string): boolean {
  return Object.entries(REPORT_MODULE_DECISION_TITLES).every(([id, title]) =>
    new RegExp(`^##\\s+M${id}\\s+${escapeRegExp(title)}\\s*$`, 'mu').test(markdown)
  )
}

export function reportModuleDecisionHeading(moduleId: number, title: string): string {
  const numeral = REPORT_MODULE_DECISION_NUMERALS[moduleId - 1]
  return numeral ? `内容洞察决策${numeral}：${title.trim()}` : `M${moduleId} ${title.trim()}`
}

/** Split the user-facing report at M4 so the independent material cloud stays in that module. */
export function splitReportAtSellingPoints(markdown: string): [string, string] | null {
  const heading = /^##[ \t]+(?:内容洞察决策四[：:][ \t]*|M4[ \t]+)卖点提炼与排序[ \t]*$/mu.exec(markdown)
  if (!heading || heading.index === undefined) return null
  const end = heading.index + heading[0].length
  return [markdown.slice(0, end), markdown.slice(end)]
}

export function parseReportModuleDecisionHeading(
  value: string
): { moduleId: number; title: string } | null {
  const hit = value.trim().match(/^内容洞察决策([一二三四五六])\s*[：:]\s*(.+)$/u)
  if (!hit) return null
  const moduleId = REPORT_MODULE_DECISION_NUMERALS.indexOf(hit[1] as typeof REPORT_MODULE_DECISION_NUMERALS[number]) + 1
  return moduleId > 0 ? { moduleId, title: hit[2].trim() } : null
}

function reportModuleHeadingsForDisplay(markdown: string): string {
  if (!isCurrentSixModuleReport(markdown)) return markdown
  return markdown.replace(/^##\s+M([1-6])\s+(.+?)\s*$/gmu, (line, rawId: string, title: string) => {
    const moduleId = Number(rawId)
    if (REPORT_MODULE_DECISION_TITLES[moduleId] !== title.trim()) return line
    return `## ${reportModuleDecisionHeading(moduleId, title)}`
  })
}

export function buildEvidenceSourceNameMap(
  details: ReadonlyArray<{ name: string; text: string }>
): Record<string, string> {
  const result: Record<string, string> = {}
  for (const detail of details) {
    const safeName = detail.name.replace(/[\r\n]+/gu, ' ').replace(/\|/gu, '／').trim()
    if (!safeName) continue
    for (const match of detail.text.matchAll(EVIDENCE_ID_VALUE)) {
      result[match[0].toUpperCase()] = safeName
    }
  }
  return result
}

/**
 * Keeps traceable evidence IDs in the internal report while replacing them in
 * every user-facing surface with a plain-language provenance label.
 */
export function reportMarkdownForDisplay(
  markdown: string,
  sourceNames: EvidenceSourceNameMap = {}
): string {
  return reportModuleHeadingsForDisplay(markdown)
    .replace(EVIDENCE_ID_SEQUENCE, (sequence) => {
      const names = [...sequence.matchAll(EVIDENCE_ID_VALUE)]
        .map((match) => sourceNames[match[0].toUpperCase()])
        .filter((name): name is string => Boolean(name))
      const uniqueNames = [...new Set(names)]
      return uniqueNames.length ? uniqueNames.join('、') : '已核验资料'
    })
    .replace(/已核验资料(?:\s*[、,，；;]\s*已核验资料)+/gu, '已核验资料')
}
