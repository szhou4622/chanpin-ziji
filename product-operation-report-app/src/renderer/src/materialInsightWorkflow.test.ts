import { afterEach, describe, expect, it, vi } from 'vitest'
import { createHash } from 'node:crypto'
import type { ChatMessage, ModelTaskContext, ProjectTaskSnapshot } from '../../shared/types'
import { materialInsightTaskPrefix, readMaterialInsightResult, runMaterialInsightWorkflow } from './materialInsightWorkflow'
import { materialInsightFingerprint, type MaterialInsightRow } from './materialInsights'

const priorWindow = globalThis.window
afterEach(() => { (globalThis as { window: Window }).window = priorWindow })

describe('material insight checkpoints', () => {
  const sampleRows: MaterialInsightRow[] = [{
    sourceId: 'source', sourceName: '素材.csv', sheetName: 'Sheet1', rowEvidenceId: 'R-1',
    materialKey: 'M-1', product: '产品甲', attribution: '自有数据', platform: '视频号',
    sellingPoint: 'Top1：安装方便', needScene: '下班回家安装'
  }]

  it('excludes competitors before model calls, ignores old mixed caches and restores only own evidence after reopening', async () => {
    const rows = [...sampleRows, { ...sampleRows[0], sourceId: 'competitor', rowEvidenceId: 'C-1',
      materialKey: 'C-1', product: '竞品乙', attribution: '竞品数据', sellingPoint: 'Top1：竞品专属赠品' }]
    const legacyId = 'own-test:material-insight:v1:12345678-200-2:extract-0001'
    const legacyTask: ProjectTaskSnapshot = { kind: 'module', status: 'complete', output: '原账单正文',
      billingAttemptId: 'legacy-receipt', billingConfirmed: true, updatedAt: '2026-01-01T00:00:00.000Z' }
    const journal: Record<string, ProjectTaskSnapshot> = { [legacyId]: legacyTask }
    const fingerprint = materialInsightFingerprint(rows, ['产品甲', '竞品乙'])
    const finalId = `${materialInsightTaskPrefix('own-test', fingerprint)}:final`
    // Even a legacy result copied to the new key must not qualify as an own-only cache.
    journal[finalId] = { kind: 'module', status: 'complete', updatedAt: legacyTask.updatedAt,
      output: JSON.stringify({ version: 1, fingerprint, totalMaterials: 2, items: [], mappings: [] }) }
    expect(readMaterialInsightResult(journal, 'own-test', fingerprint)).toBeNull()
    const sendChat = vi.fn((messages: ChatMessage[], context: ModelTaskContext, handlers: Parameters<typeof window.api.sendChat>[2]) => {
      expect(JSON.stringify(messages)).not.toContain('竞品专属赠品')
      expect(context.taskKey).toMatch(/^own-test:material-insight:v1:[a-f0-9]{8}-\d+-1:(?:extract-\d+|normalize-\d+-\d+)$/u)
      const input = JSON.parse(messages[1].content as string) as Array<{ id: string }> | string[]
      const output = context.taskKey.includes(':extract-')
        ? { items: (input as Array<{ id: string }>).map(({ id }) => ({ id, phrases: [{ phrase: '安装方便', evidence: '安装方便' }] })) }
        : { mappings: (input as string[]).map((raw) => ({ raw, keyword: raw })) }
      queueMicrotask(() => handlers.onDone?.(JSON.stringify(output)))
      return { abort: () => undefined }
    })
    const testWindow = { setTimeout, clearTimeout, api: { sendChat } }
    ;(globalThis as unknown as { window: typeof testWindow }).window = testWindow
    const run = () => runMaterialInsightWorkflow({ rows, selectedProducts: ['产品甲', '竞品乙'],
      scopeLabel: '产品甲、竞品乙', sessionId: 'own-test', sourceCount: 2, imageCount: 0,
      getTask: (id) => journal[id], saveTask: (id, task) => { journal[id] = task; return Promise.resolve() },
      setAbort: () => undefined, onProgress: () => undefined })
    const result = await run()
    expect(result).toMatchObject({ sourceScope: 'own', totalMaterials: 1, effectiveMaterials: 1, scopeLabel: '产品甲' })
    expect(sendChat).toHaveBeenCalledTimes(2)
    expect(journal[legacyId]).toEqual(legacyTask)
    const persisted = JSON.parse(journal[finalId].output!)
    expect(persisted.items[0].evidence).toEqual([])
    const reopenedJournal = JSON.parse(JSON.stringify(journal)) as typeof journal
    const restored = readMaterialInsightResult(reopenedJournal, 'own-test', fingerprint)!
    expect(restored.items[0].evidence).toHaveLength(1)
    expect(restored.mappings.every((mapping) => mapping.sourceId === 'source')).toBe(true)
    expect(restored.items[0].evidence[0].sourceId).toBe('source')
    await run()
    expect(sendChat).toHaveBeenCalledTimes(2)
  })

  it('returns a truthful empty cloud without any model calls when only competitor or unconfirmed material exists', async () => {
    const sendChat = vi.fn()
    const testWindow = { setTimeout, clearTimeout, api: { sendChat } }
    ;(globalThis as unknown as { window: typeof testWindow }).window = testWindow
    const journal: Record<string, ProjectTaskSnapshot> = {}
    const result = await runMaterialInsightWorkflow({
      rows: [{ ...sampleRows[0], attribution: '竞品数据' }, { ...sampleRows[0], attribution: '' }],
      selectedProducts: ['产品甲'], scopeLabel: '产品甲', sessionId: 'empty-own', sourceCount: 2, imageCount: 0,
      getTask: (id) => journal[id], saveTask: (id, task) => { journal[id] = task; return Promise.resolve() },
      setAbort: () => undefined, onProgress: () => undefined
    })
    expect(result).toMatchObject({ sourceScope: 'own', scopeLabel: '自有素材', totalMaterials: 0,
      effectiveMaterials: 0, normalizedCount: 0, items: [], mappings: [] })
    expect(sendChat).not.toHaveBeenCalled()
  })

  it('retries a saved extraction receipt after timeout without regenerating or changing its raw output hash', async () => {
    const journal: Record<string, ProjectTaskSnapshot> = {}
    const calls: Record<string, number> = {}
    const charges = new Set<string>()
    let loseReply = true
    const confirm = vi.fn((receipt: { requestId: string; logicalTaskId: string; outputSha256: string }) => {
      expect(journal[receipt.logicalTaskId]?.status).toBe('complete')
      expect(receipt.outputSha256).toBe(createHash('sha256').update(journal[receipt.logicalTaskId].output!).digest('hex'))
      charges.add(receipt.requestId)
      if (loseReply) {
        loseReply = false
        return Promise.reject(new Error('confirmation reply lost'))
      }
      return Promise.resolve({ state: 'charged', chargedUnits: 1_000_000 })
    })
    const testWindow = { setTimeout, clearTimeout, api: {
      confirmSavedModelResult: confirm,
      sendChat: (messages: ChatMessage[], context: ModelTaskContext, handlers: Parameters<typeof window.api.sendChat>[2]) => {
        calls[context.taskKey] = (calls[context.taskKey] || 0) + 1
        const input = JSON.parse(messages[1].content as string) as Array<{ id: string }> | string[]
        const output = context.taskKey.includes(':extract-')
          ? { items: (input as Array<{ id: string }>).map(({ id }) => ({ id, phrases: [{ phrase: '安装方便', evidence: '安装方便' }] })) }
          : { mappings: (input as string[]).map((raw) => ({ raw, keyword: raw })) }
        const text = `\n${JSON.stringify(output)}\n`
        queueMicrotask(() => handlers.onDone?.(text, context.taskKey, createHash('sha256').update(text).digest('hex')))
        return { abort: () => undefined }
      }
    } }
    ;(globalThis as unknown as { window: typeof testWindow }).window = testWindow
    const run = () => runMaterialInsightWorkflow({
      rows: sampleRows, selectedProducts: ['产品甲'], scopeLabel: '产品甲', sessionId: 'receipt-test',
      sourceCount: 1, imageCount: 0, getTask: (id) => journal[id],
      saveTask: (id, task) => { journal[id] = task; return Promise.resolve() },
      setAbort: () => undefined, onProgress: () => undefined
    })
    await expect(run()).rejects.toThrow('confirmation reply lost')
    const extractionId = Object.keys(calls)[0]
    expect(journal[extractionId]).toMatchObject({ status: 'complete', billingAttemptId: extractionId })
    expect((await run()).items[0].keyword).toBe('安装方便')
    expect(calls[extractionId]).toBe(1)
    expect(journal[extractionId].billingConfirmed).toBe(true)
    expect(confirm).toHaveBeenCalledTimes(3)
    expect(charges.size).toBe(2)
  })

  it('keeps cancellation active while saving a completed batch and does not start normalization after stop', async () => {
    const journal: Record<string, ProjectTaskSnapshot> = {}
    const abortCallbacks: Array<(() => void) | null> = []
    let releaseSave!: () => void
    const sendChat = vi.fn((messages: ChatMessage[], _context: ModelTaskContext, handlers: Parameters<typeof window.api.sendChat>[2]) => {
      const input = JSON.parse(messages[1].content as string) as Array<{ id: string }>
      queueMicrotask(() => handlers.onDone?.(JSON.stringify({ items: input.map(({ id }) => ({
        id, phrases: [{ phrase: '安装方便', evidence: '安装方便' }]
      })) })))
      return { abort: () => undefined }
    })
    const testWindow = { setTimeout, clearTimeout, api: { sendChat } }
    ;(globalThis as unknown as { window: typeof testWindow }).window = testWindow
    const run = runMaterialInsightWorkflow({
      rows: sampleRows, selectedProducts: ['产品甲'], scopeLabel: '产品甲', sessionId: 'stop-test',
      sourceCount: 1, imageCount: 0, getTask: (id) => journal[id],
      saveTask: (id, task) => { journal[id] = task; return new Promise((resolve) => { releaseSave = resolve }) },
      setAbort: (fn) => abortCallbacks.push(fn), onProgress: () => undefined
    })
    await vi.waitFor(() => expect(releaseSave).toBeTypeOf('function'))
    expect(abortCallbacks.at(-1)).toBeTypeOf('function')
    abortCallbacks.at(-1)?.()
    releaseSave()
    await expect(run).rejects.toThrow('已停止')
    expect(sendChat).toHaveBeenCalledTimes(1)
    expect(abortCallbacks.at(-1)).toBeNull()
  })

  it('resumes only the failed extraction batch without rerunning a completed batch', async () => {
    const rows: MaterialInsightRow[] = Array.from({ length: 45 }, (_, index) => ({
      sourceId: 'source', sourceName: '素材.csv', sheetName: 'Sheet1', rowEvidenceId: `R-${index + 1}`,
      materialKey: `M-${index + 1}`, product: '产品甲', attribution: '自有数据', platform: '视频号',
      sellingPoint: `Top1：${index % 2 ? '便于安装' : '安装方便'}${'说明'.repeat(230)}${index}`, needScene: '下班回家安装'
    }))
    const journal: Record<string, ProjectTaskSnapshot> = {}
    const calls: Record<string, number> = {}
    let failSecond = true
    const testWindow = {
      setTimeout: globalThis.setTimeout.bind(globalThis),
      clearTimeout: globalThis.clearTimeout.bind(globalThis),
      api: {
        sendChat: (messages: ChatMessage[], context: ModelTaskContext, handlers: {
          onDone?: (full: string) => void; onError?: (message: string) => void
        }) => {
          calls[context.taskKey] = (calls[context.taskKey] || 0) + 1
          const timer = globalThis.setTimeout(() => {
            if (context.taskKey.endsWith(':extract-0002') && failSecond) {
              handlers.onError?.('模拟网络中断')
              return
            }
            const input = JSON.parse(messages[1].content as string) as Array<{ id?: string; text?: string }> | string[]
            const output = context.taskKey.includes(':extract-')
              ? { items: (input as Array<{ id: string; text: string }>).map(({ id, text }) => ({
                  id, phrases: text.includes('安装方便')
                    ? [{ phrase: '安装方便', evidence: '安装方便' }]
                    : text.includes('便于安装') ? [{ phrase: '便于安装', evidence: '便于安装' }] : []
                })) }
              : { mappings: (input as string[]).map((raw) => ({ raw, keyword: raw === '便于安装' ? '安装方便' : raw })) }
            handlers.onDone?.(JSON.stringify(output))
          }, 0)
          return { abort: () => { clearTimeout(timer); handlers.onError?.('已停止') } }
        }
      }
    }
    ;(globalThis as unknown as { window: typeof testWindow }).window = testWindow
    const run = () => runMaterialInsightWorkflow({
      rows, selectedProducts: ['产品甲'], scopeLabel: '产品甲', sessionId: 'report-test',
      sourceCount: 1, imageCount: 0, getTask: (id) => journal[id],
      saveTask: (id, task) => { journal[id] = task; return Promise.resolve() },
      setAbort: () => undefined, onProgress: () => undefined
    })
    await expect(run()).rejects.toThrow()
    const firstKey = Object.keys(calls).find((key) => key.endsWith(':extract-0001'))!
    expect(journal[firstKey]?.status).toBe('complete')
    failSecond = false
    const insight = await run()
    expect(calls[firstKey]).toBe(1)
    expect(insight.totalMaterials).toBe(45)
    expect(insight.items[0].materialCount).toBe(45)
    expect(insight.items[0].top1Count).toBe(45)
    const callsAfterSuccess = Object.values(calls).reduce((sum, count) => sum + count, 0)
    const restored = await run()
    expect(restored.items[0].evidence).toHaveLength(45)
    expect(Object.values(calls).reduce((sum, count) => sum + count, 0)).toBe(callsAfterSuccess)
  })
})
