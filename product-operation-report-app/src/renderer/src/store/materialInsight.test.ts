import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ChatMessage, MaterialSellingPointInsight, ModelTaskContext, SceneCatalogEntry } from '../../../shared/types'
import { REPORT_MODULES_V2 } from '../../../shared/types'
import { useStore } from '../store'
import { computeSellingPointInsight, materialInsightFingerprint, readMaterialInsightRows, selectOwnMaterialInsightScope } from '../materialInsights'
import { readMaterialInsightResult } from '../materialInsightWorkflow'

beforeEach(() => { useStore.setState(useStore.getInitialState(), true) })
afterEach(() => { vi.unstubAllGlobals() })

describe('own-material cloud recovery and export', () => {
  it.each(['missing-no-material', 'legacy-empty', 'current-own'])('reuses a complete %s cache before any points or model call', async (mode) => {
    const markdown = ['# 产品内容策略报告', ...[...REPORT_MODULES_V2].sort((a, b) => a.id - b.id)
      .map((module) => `## M${module.id} ${module.title}\n已有报告内容`),
    '> 本报告内容由 AI 生成，请谨慎参考。'].join('\n\n')
    const source = mode === 'missing-no-material'
      ? { id: 'product', name: '产品.md', kind: 'doc' as const, kindV1: 'product-supply' as const,
          attribution: '自有数据', text: '产品事实' }
      : { id: 'own', name: '自有.csv', kind: 'table' as const, kindV1: 'material-data' as const,
          attribution: '自有数据', text: mode === 'legacy-empty'
            ? '素材ID,产品,标题\na,产品甲,只有标题'
            : '素材ID,产品,卖点排序\na,产品甲,Top1：安装方便' }
    const scope = selectOwnMaterialInsightScope(readMaterialInsightRows([source]), [])
    const currentInsight = computeSellingPointInsight({ rows: scope.rows, scopeLabel: scope.label,
      fingerprint: materialInsightFingerprint(scope.rows, scope.selectedProducts), candidates: [], normalization: {} })
    const snapshot = {
      cleanedData: '清洗结果', cleanDetails: [{ name: source.name, text: '清洗结果' }],
      artifacts: { ...Object.fromEntries(REPORT_MODULES_V2.map((module) => [module.id, '已有报告内容'])), 9: markdown },
      reportMarkdown: markdown,
      materialInsight: mode === 'missing-no-material' ? undefined : mode === 'current-own' ? currentInsight : {
        version: 1 as const, fingerprint: 'legacy-empty-cache', scopeLabel: '本次上传素材',
        totalMaterials: 0, effectiveMaterials: 0, normalizedCount: 0, items: [], mappings: []
      }
    }
    const canStartPointsReport = vi.fn(() => { throw new Error('must offer cached report without checking points') })
    const sendChat = vi.fn(() => { throw new Error('cached report must not call a model') })
    vi.stubGlobal('window', { setTimeout, clearTimeout, api: {
      lookupReportResultCache: () => Promise.resolve({ hit: true, cacheKey: 'cache-test', snapshot }),
      canStartPointsReport, sendChat, recordCostOptimization: () => Promise.resolve(true),
      saveLastProject: () => Promise.resolve()
    } })
    useStore.setState({ analysisSessionId: 'cache-own', phase: 'idle', sources: [source], selectedMaterialProducts: [] })
    await useStore.getState().startGeneration()
    expect(useStore.getState().reportReuseOffer?.cacheKey).toBe('cache-test')
    await useStore.getState().acceptReportReuse()
    expect(canStartPointsReport).not.toHaveBeenCalled()
    expect(sendChat).not.toHaveBeenCalled()
    expect(useStore.getState().reportMarkdown).toBe(markdown)
    expect(useStore.getState().phase).toBe('done')
    const restored = readMaterialInsightResult(useStore.getState().taskJournal, 'cache-own', currentInsight.fingerprint)!
    expect(restored.sourceScope).toBe('own')
    expect(restored.totalMaterials).toBe(mode === 'missing-no-material' ? 0 : 1)
    expect(restored.mappings).toEqual([])
  })

  it('does not offer a legacy cloud with competitor content as an own-only cached report', async () => {
    const markdown = ['# 产品内容策略报告', ...[...REPORT_MODULES_V2].sort((a, b) => a.id - b.id)
      .map((module) => `## M${module.id} ${module.title}\n已有报告内容`),
    '> 本报告内容由 AI 生成，请谨慎参考。'].join('\n\n')
    const source = { id: 'own', name: '自有.csv', kind: 'table' as const, kindV1: 'material-data' as const,
      attribution: '自有数据', text: '素材ID,产品,卖点排序\na,产品甲,Top1：安装方便' }
    const snapshot = { cleanedData: '清洗结果', cleanDetails: [{ name: source.name, text: '清洗结果' }],
      artifacts: { ...Object.fromEntries(REPORT_MODULES_V2.map((module) => [module.id, '已有报告内容'])), 9: markdown },
      reportMarkdown: markdown, materialInsight: { version: 1, fingerprint: 'old-mixed', scopeLabel: '混合素材',
        totalMaterials: 2, effectiveMaterials: 2, normalizedCount: 1,
        items: [{ keyword: '竞品专属赠品' }], mappings: [{ sourceId: 'competitor' }] } }
    const startPaidGeneration = vi.fn(() => Promise.resolve())
    vi.stubGlobal('window', { setTimeout, clearTimeout, api: {
      lookupReportResultCache: () => Promise.resolve({ hit: true, cacheKey: 'old-mixed', snapshot })
    } })
    useStore.setState({ sources: [source], _startPaidGeneration: startPaidGeneration })
    await useStore.getState().startGeneration()
    expect(useStore.getState().reportReuseOffer).toBeNull()
    expect(startPaidGeneration).toHaveBeenCalledOnce()
  })

  it('retries only the cloud while preserving report receipts, and exports own-only statistics with competitor scenes intact', async () => {
    const markdown = ['# 产品内容策略报告', ...[...REPORT_MODULES_V2].sort((a, b) => a.id - b.id)
      .map((module) => `## M${module.id} ${module.title}\n已有报告内容`),
    '> 本报告内容由 AI 生成，请谨慎参考。'].join('\n\n')
    const priorReceipt = { kind: 'module' as const, status: 'complete' as const, output: '已付费结果',
      billingAttemptId: 'existing-receipt', billingConfirmed: true, updatedAt: '2026-01-01T00:00:00.000Z' }
    const sources = [
      { id: 'own', name: '自有.csv', kind: 'table' as const, kindV1: 'material-data' as const, attribution: '自有数据',
        text: '素材ID,产品,卖点排序,需求场景\na,产品甲,Top1：安装方便,自有场景' },
      { id: 'competitor', name: '竞品.csv', kind: 'table' as const, kindV1: 'material-data' as const, attribution: '竞品数据',
        text: '素材ID,产品,卖点排序,需求场景\nb,产品甲,Top1：竞品专属赠品,竞品场景' }
    ]
    const artifacts = { ...Object.fromEntries(REPORT_MODULES_V2.map((module) => [module.id, '已有报告内容'])), 9: markdown }
    const moduleStates = Object.fromEntries(REPORT_MODULES_V2.map((module) => [module.key,
      { status: 'done' as const, updatedAt: priorReceipt.updatedAt }]))
    useStore.setState({ analysisSessionId: 'own-store', phase: 'done', sources,
      cleanDetails: sources.map((source) => ({ id: source.id, name: source.name, text: source.text })),
      selectedMaterialProducts: ['产品甲'], artifacts, moduleStates, reportMarkdown: markdown,
      cleanedData: '已清洗资料', taskJournal: { 'old-module': priorReceipt, 'old-cloud': priorReceipt } })
    const sendChat = vi.fn((messages: ChatMessage[], context: ModelTaskContext, handlers: Parameters<typeof window.api.sendChat>[2]) => {
      expect(context.stepId).toBe('material-selling-cloud')
      expect(JSON.stringify(messages)).not.toContain('竞品专属赠品')
      const input = JSON.parse(messages[1].content as string) as Array<{ id: string }> | string[]
      const output = context.taskKey.includes(':extract-')
        ? { items: (input as Array<{ id: string }>).map(({ id }) => ({ id, phrases: [{ phrase: '安装方便', evidence: '安装方便' }] })) }
        : { mappings: (input as string[]).map((raw) => ({ raw, keyword: raw })) }
      queueMicrotask(() => handlers.onDone?.(JSON.stringify(output)))
      return { abort: () => undefined }
    })
    const exportHtml = vi.fn((_markdown: string, _name: string,
      _insight?: MaterialSellingPointInsight, _status?: string, _scenes?: SceneCatalogEntry[]) => Promise.resolve({ ok: true, path: 'report.html' }))
    vi.stubGlobal('window', { setTimeout, clearTimeout, api: {
      sendChat, saveLastProject: vi.fn(() => Promise.resolve()), exportHtml
    } })
    await useStore.getState().retryMaterialInsight()
    const state = useStore.getState()
    expect(sendChat).toHaveBeenCalledTimes(2)
    expect(state.phase).toBe('done')
    expect(state.artifacts).toEqual(artifacts)
    expect(state.moduleStates).toEqual(moduleStates)
    expect(state.taskJournal['old-module']).toEqual(priorReceipt)
    expect(state.taskJournal['old-cloud']).toEqual(priorReceipt)
    const scope = selectOwnMaterialInsightScope(readMaterialInsightRows(state.sources), state.selectedMaterialProducts)
    const restored = readMaterialInsightResult(JSON.parse(JSON.stringify(state.taskJournal)), state.analysisSessionId,
      materialInsightFingerprint(scope.rows, scope.selectedProducts))!
    expect(restored.totalMaterials).toBe(1)
    expect(restored.mappings.map((mapping) => mapping.sourceId)).toEqual(['own'])
    expect(restored.items[0].evidence[0].sourceId).toBe('own')
    await state.exportReport('html')
    expect(exportHtml).toHaveBeenCalledOnce()
    const [, , exported, status, scenes] = exportHtml.mock.calls[0]
    expect(status).toBe('ready')
    expect(exported).toMatchObject({ sourceScope: 'own', totalMaterials: 1, effectiveMaterials: 1 })
    expect(exported!.items.flatMap((item) => item.evidence).every((item) => item.sourceId === 'own')).toBe(true)
    expect(scenes!.some((scene) => scene.attribution === '竞品数据' && scene.text === '竞品场景')).toBe(true)
  })
})
