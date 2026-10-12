import { afterEach, describe, expect, it, vi } from 'vitest'
import { createHash } from 'node:crypto'
import type { ChatMessage, ModelTaskContext, ProjectTaskSnapshot } from '../../shared/types'
import { runMaterialInsightWorkflow } from './materialInsightWorkflow'
import type { MaterialInsightRow } from './materialInsights'

const priorWindow = globalThis.window
afterEach(() => { (globalThis as { window: Window }).window = priorWindow })

describe('material insight checkpoints', () => {
  const sampleRows: MaterialInsightRow[] = [{
    sourceId: 'source', sourceName: '素材.csv', sheetName: 'Sheet1', rowEvidenceId: 'R-1',
    materialKey: 'M-1', product: '产品甲', attribution: '自有数据', platform: '视频号',
    sellingPoint: 'Top1：安装方便', needScene: '下班回家安装'
  }]

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
