import { beforeEach, describe, expect, it, vi } from 'vitest'
import { webcrypto } from 'node:crypto'
import { billingProof, confirmSavedResult, confirmSavedTask, rejectIncompleteResult, sha256Hex } from './billing'

const confirm = vi.fn()
const reject = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('crypto', webcrypto)
  vi.stubGlobal('window', {
    api: { confirmSavedModelResult: confirm, rejectModelResult: reject }
  })
})

describe('saved-result billing receipt', () => {
  it('sends only IDs and digests after a recoverable result is saved', async () => {
    confirm.mockResolvedValue({ state: 'charged', chargedUnits: 1_131_120 })
    const providerDigest = await sha256Hex('raw model output')
    const result = await confirmSavedResult('logical-1', {
      ok: true, text: 'raw model output', requestId: 'attempt-1', outputSha256: providerDigest
    }, 'locally saved output')
    expect(result).toEqual({ state: 'charged', chargedUnits: 1_131_120 })
    expect(confirm).toHaveBeenCalledWith({
      requestId: 'attempt-1', logicalTaskId: 'logical-1', outputSha256: providerDigest,
      savedOutputSha256: await sha256Hex('locally saved output')
    })
    expect(JSON.stringify(confirm.mock.calls)).not.toContain('locally saved output')
    expect(billingProof({ ok: true, text: 'raw model output', requestId: 'attempt-1', outputSha256: providerDigest }))
      .toEqual({ billingAttemptId: 'attempt-1', billingOutputSha256: providerDigest })
  })

  it('keeps old-client-compatible behavior when billing proof is absent', async () => {
    expect(await confirmSavedResult('logical-1', { ok: true, text: 'saved' }, 'saved'))
      .toEqual({ state: 'legacy', chargedUnits: 0 })
    expect(confirm).not.toHaveBeenCalled()
  })

  it('uses the original provider digest and separate saved digest when restoring a formatted result', async () => {
    confirm.mockResolvedValue({ state: 'charged', chargedUnits: 1_000_000 })
    const raw = '  ## 标题\n\n带 空格的文本\n'
    const output = raw.trim()
    const outputSha256 = await sha256Hex(raw)
    await confirmSavedTask('journal-key', {
      kind: 'module', status: 'complete', output, updatedAt: '2026-10-12T00:00:00Z',
      billingAttemptId: 'attempt-original', billingLogicalTaskId: 'logical-original', billingOutputSha256: outputSha256
    })
    expect(confirm).toHaveBeenCalledWith({
      requestId: 'attempt-original', logicalTaskId: 'logical-original', outputSha256,
      savedOutputSha256: await sha256Hex(output)
    })
    expect(await sha256Hex(output)).not.toBe(outputSha256)
  })

  it('rejects unusable output before retrying the same logical task', async () => {
    reject.mockResolvedValue(undefined)
    await rejectIncompleteResult('logical-1', { ok: true, text: 'incomplete', requestId: 'attempt-1' })
    expect(reject).toHaveBeenCalledWith({ requestId: 'attempt-1', logicalTaskId: 'logical-1' })
  })
})
