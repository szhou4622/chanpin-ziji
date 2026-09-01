const SHA256_HEX = /^[A-F0-9]{64}$/u

/** Bump only when persisted cleaning evidence identity semantics change. */
export const EVIDENCE_ID_VERSION = 'evidence-id-v2-sha256-source'
export const LEGACY_EVIDENCE_SCOPE_PATTERN = '[A-F0-9]{8}'
export const CONTENT_EVIDENCE_SCOPE_PATTERN = '[A-F0-9]{24}(?:-[A-Z0-9]{1,12})?'
export const EVIDENCE_SCOPE_PATTERN = `(?:${LEGACY_EVIDENCE_SCOPE_PATTERN}|${CONTENT_EVIDENCE_SCOPE_PATTERN})`
export const EVIDENCE_ID_PATTERN = `POR-[RTI]-${EVIDENCE_SCOPE_PATTERN}-\\d{6}`
export const EVIDENCE_BATCH_RECEIPT_PATTERN = `POR-B-${EVIDENCE_SCOPE_PATTERN}-\\d{4}\\|ROWS:\\d+-\\d+\\|COUNT:\\d+`
export const EVIDENCE_VALUE_PATTERN = `(?:${EVIDENCE_ID_PATTERN}|${EVIDENCE_BATCH_RECEIPT_PATTERN})`

export function normalizeSha256(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined
  const normalized = value.trim().toUpperCase()
  return SHA256_HEX.test(normalized) ? normalized : undefined
}

/**
 * Compact evidence scope for newly ingested sources.
 *
 * The full 256-bit digest is persisted on Source. Evidence IDs use a 96-bit digest
 * prefix plus up to 48 bits of the stable per-project Source id so repeated uploads
 * of identical content do not share row/image identifiers inside one report.
 */
export function evidenceScopeFromContentHash(contentHash: unknown, sourceId: unknown): string | undefined {
  const hash = normalizeSha256(contentHash)
  if (!hash) return undefined
  const sourceToken = typeof sourceId === 'string'
    ? sourceId.replace(/[^A-Za-z0-9]/gu, '').toUpperCase().slice(0, 12)
    : ''
  return `${hash.slice(0, 24)}${sourceToken ? `-${sourceToken}` : ''}`
}
