import { afterEach, describe, expect, it } from 'vitest'
import type { ChatMessage, ModelTaskContext, ProjectTaskSnapshot } from '../../shared/types'
import { runMaterialInsightWorkflow } from './materialInsightWorkflow'
import type { MaterialInsightRow } from './materialInsights'

const priorWindow = globalThis.window
afterEach(() => { (globalThis as { window: Window }).window = priorWindow })

describe('material insight checkpoints', () => {
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
