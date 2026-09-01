import { describe, expect, it } from 'vitest'
import {
  EVIDENCE_BATCH_RECEIPT_PATTERN,
  EVIDENCE_ID_PATTERN,
  evidenceScopeFromContentHash,
  normalizeSha256
} from './evidenceIdentity'

describe('evidence identity', () => {
  it('normalizes only complete SHA-256 values', () => {
    expect(normalizeSha256('ab'.repeat(32))).toBe('AB'.repeat(32))
    expect(normalizeSha256('abc')).toBeUndefined()
  })

  it('derives a compact content-backed scope while separating duplicate source instances', () => {
    const hash = 'ab'.repeat(32)
    expect(evidenceScopeFromContentHash(hash, '12345678-90ab-4def-8123-456789abcdef'))
      .toBe('ABABABABABABABABABABABAB-1234567890AB')
    expect(evidenceScopeFromContentHash(hash, 'fedcba98-7654-4321-8123-456789abcdef'))
      .not.toBe(evidenceScopeFromContentHash(hash, '12345678-90ab-4def-8123-456789abcdef'))
  })

  it('keeps both legacy and content-backed evidence formats readable', () => {
    const evidence = new RegExp(`^${EVIDENCE_ID_PATTERN}$`, 'u')
    const receipt = new RegExp(`^${EVIDENCE_BATCH_RECEIPT_PATTERN}$`, 'u')
    expect(evidence.test('POR-R-32F24FA0-000001')).toBe(true)
    expect(evidence.test('POR-T-ABABABABABABABABABABABAB-1234567890AB-000001')).toBe(true)
    expect(receipt.test('POR-B-ABCDEF12-0001|ROWS:1-50|COUNT:50')).toBe(true)
    expect(receipt.test('POR-B-ABABABABABABABABABABABAB-1234567890AB-0001|ROWS:1-50|COUNT:50')).toBe(true)
  })
})
