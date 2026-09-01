import { EVIDENCE_VALUE_PATTERN } from './evidenceIdentity'

const EVIDENCE_ID_ATOM = [
  '`{0,2}',
  `(?:${EVIDENCE_VALUE_PATTERN})`,
  '`{0,2}'
].join('')

const EVIDENCE_ID_SEQUENCE = new RegExp(
  `${EVIDENCE_ID_ATOM}(?:\\s*(?:[、,，；;]|和|及|/)\\s*${EVIDENCE_ID_ATOM})*`,
  'giu'
)

const EVIDENCE_ID_VALUE = new RegExp(EVIDENCE_VALUE_PATTERN, 'giu')

export type EvidenceSourceNameMap = Readonly<Record<string, string>>

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
  return markdown
    .replace(EVIDENCE_ID_SEQUENCE, (sequence) => {
      const names = [...sequence.matchAll(EVIDENCE_ID_VALUE)]
        .map((match) => sourceNames[match[0].toUpperCase()])
        .filter((name): name is string => Boolean(name))
      const uniqueNames = [...new Set(names)]
      return uniqueNames.length ? uniqueNames.join('、') : '已核验资料'
    })
    .replace(/已核验资料(?:\s*[、,，；;]\s*已核验资料)+/gu, '已核验资料')
}
