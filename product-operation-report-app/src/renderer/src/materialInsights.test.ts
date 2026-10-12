import { describe, expect, it } from 'vitest'
import {
  buildSceneCatalog,
  computeSellingPointInsight,
  materialInsightFingerprint,
  parseSellingPointDescriptions,
  readMaterialInsightRows,
  selectMaterialInsightScope,
  validateSceneSelection
} from './materialInsights'
import {
  buildExtractionJobs,
  expandExtractedPhrases,
  parseExtractionReply,
  parseNormalizationReply
} from './materialInsightModel'

const sources = [{
  id: 'file-a', name: '内容分析表.xlsx', kind: 'table' as const, kindV1: 'material-data' as const,
  attribution: '自有数据', platform: '视频号',
  text: [
    '### 工作表：自有素材',
    '素材ID,产品,卖点排序,需求场景',
    'v1,产品甲,"Top1：通过对比展示安装过程简单\nTop3：安装方便",下班回家安装',
    'v1,产品甲,Top2：安装方便,下班回家安装',
    'v2,产品甲,价格含安装服务,周末在家安装',
    '### 工作表：其他产品',
    '素材ID,产品,卖点排序,需求场景',
    'v3,产品乙,Top1：七天内送达,办公室收货'
  ].join('\n')
}]

describe('material insight extraction and statistics', () => {
  it('reads all sheets, requires explicit scope for multiple products and does not split a phrase on commas', () => {
    const rows = readMaterialInsightRows(sources)
    expect(rows).toHaveLength(4)
    expect(selectMaterialInsightScope(rows, []).needsSelection).toBe(true)
    const scope = selectMaterialInsightScope(rows, ['产品甲'])
    expect(scope.rows).toHaveLength(3)
    const descriptions = scope.rows.flatMap(parseSellingPointDescriptions)
    expect(descriptions.map((item) => item.topRank)).toEqual([1, 3, 2, null])
    expect(descriptions[0].rawDescription).toContain('安装过程简单')
    const inline = parseSellingPointDescriptions({ ...scope.rows[0], sellingPoint: 'Top1：安装方便，Top2：含安装服务' })
    expect(inline.map((item) => item.topRank)).toEqual([1, 2])
    const unsplit = parseSellingPointDescriptions({ ...scope.rows[0], sellingPoint: '安装方便，含安装服务' })
    expect(unsplit).toHaveLength(1)
    expect(new Set(scope.rows.map((row) => row.materialKey)).size).toBe(2)
  })

  it('validates every model input and original evidence before expanding to rows', () => {
    const rows = selectMaterialInsightScope(readMaterialInsightRows(sources), ['产品甲']).rows
    const jobs = buildExtractionJobs(rows.flatMap(parseSellingPointDescriptions))
    const reply = JSON.stringify({ items: jobs[0].inputs.map((input) => ({
      id: input.id,
      phrases: input.text.includes('安装') ? [{ phrase: '安装方便', evidence: '安装' }] : []
    })) })
    const phrases = parseExtractionReply(jobs[0], reply)
    expect(phrases.length).toBeGreaterThan(0)
    expect(() => parseExtractionReply(jobs[0], '{"items":[]}')).toThrow(/覆盖/)
    expect(() => parseExtractionReply(jobs[0], JSON.stringify({ items: jobs[0].inputs.map((input) => ({
      id: input.id, phrases: [{ phrase: '编造功能', evidence: '不存在片段' }]
    })) }))).toThrow(/反查/)
    const expanded = expandExtractedPhrases(rows.flatMap(parseSellingPointDescriptions), jobs, phrases)
    expect(expanded.every((item) => item.rowEvidenceId && item.rawDescription.includes(item.evidenceSnippet))).toBe(true)
  })

  it('counts distinct materials once, uses the highest Top position and computes coverage in code', () => {
    const rows = selectMaterialInsightScope(readMaterialInsightRows(sources), ['产品甲']).rows
    const evidence = rows.flatMap(parseSellingPointDescriptions).map((description) => ({
      sourceId: description.row.sourceId, sourceName: description.row.sourceName,
      sheetName: description.row.sheetName, rowEvidenceId: description.row.rowEvidenceId,
      materialKey: description.row.materialKey, topRank: description.topRank,
      rawDescription: description.rawDescription, evidenceSnippet: description.rawDescription,
      candidate: description.rawDescription.includes('价格') ? '价格含安装服务' : '安装方便'
    }))
    const insight = computeSellingPointInsight({
      rows, scopeLabel: '产品甲', fingerprint: materialInsightFingerprint(rows, ['产品甲']),
      candidates: evidence, normalization: { 安装方便: '安装方便', 价格含安装服务: '价格含安装服务' }
    })
    expect(insight.totalMaterials).toBe(2)
    expect(insight.effectiveMaterials).toBe(2)
    const item = insight.items.find((entry) => entry.keyword === '安装方便')!
    expect(item.materialCount).toBe(1)
    expect(item.top1Count).toBe(1)
    expect(item.top2Count).toBe(0)
    expect(item.top3Count).toBe(0)
    expect(item.rankScore).toBe(3)
    expect(item.coverageRate).toBe(0.5)
    expect(item.materialCount).toBe(item.top1Count + item.top2Count + item.top3Count + item.unrankedCount)
  })

  it('includes material rows with a missing selling-point column in the coverage denominator', () => {
    const missing = readMaterialInsightRows([{ id: 'missing', name: '素材缺列.csv', kind: 'table',
      kindV1: 'material-data', attribution: '自有数据', text: '素材ID,产品,标题\nx1,产品甲,视频一' }])
    expect(missing).toHaveLength(1)
    expect(missing[0].sellingPoint).toBe('')
    expect(missing.flatMap(parseSellingPointDescriptions)).toHaveLength(0)
    const insight = computeSellingPointInsight({ rows: missing, scopeLabel: '产品甲', fingerprint: 'missing',
      candidates: [], normalization: {} })
    expect(insight.totalMaterials).toBe(1)
    expect(insight.effectiveMaterials).toBe(0)
  })

  it('does not silently merge unlabeled material with a named product', () => {
    const rows = readMaterialInsightRows([{ id: 'mixed', name: '混合素材.csv', kind: 'table',
      kindV1: 'material-data', attribution: '自有数据', text: '素材ID,产品,卖点排序\na,产品甲,Top1：安装方便\nb,,Top1：含安装服务' }])
    const scope = selectMaterialInsightScope(rows, ['产品甲'])
    expect(scope.needsSelection).toBe(true)
    expect(scope.error).toContain('未标注产品')
  })

  it('reads TSV material columns without interpreting a comma as a Top separator', () => {
    const rows = readMaterialInsightRows([{ id: 'tsv', name: '素材.tsv', kind: 'table',
      kindV1: 'material-data', productName: '产品甲', attribution: '自有数据',
      text: '素材ID\t卖点排序\t需求场景\na1\t安装方便，含安装服务\t周末在家安装' }])
    expect(rows).toHaveLength(1)
    expect(rows[0].needScene).toBe('周末在家安装')
    expect(parseSellingPointDescriptions(rows[0])).toHaveLength(1)
  })

  it('reports malformed quoted material rows instead of silently treating them as empty', () => {
    const diagnostics: string[] = []
    const rows = readMaterialInsightRows([{ id: 'bad', name: '损坏.csv', kind: 'table',
      kindV1: 'material-data', text: '素材ID,卖点排序,需求场景\na1,"未关闭引号,早餐' }], diagnostics)
    expect(rows).toHaveLength(0)
    expect(diagnostics[0]).toContain('无法可靠解析')
  })

  it('treats rows without a reliable material ID as distinct even across duplicate file names', () => {
    const base = { name: '同名素材.csv', kind: 'table' as const, kindV1: 'material-data' as const,
      attribution: '自有数据', text: '标题,卖点排序\n同名标题,Top1：安装方便' }
    const rows = readMaterialInsightRows([{ ...base, id: 'one' }, { ...base, id: 'two' }])
    expect(rows).toHaveLength(2)
    expect(rows[0].materialKey).not.toBe(rows[1].materialKey)
  })

  it('keeps all 50 top-level material tables in the local evidence denominator', () => {
    const many = readMaterialInsightRows(Array.from({ length: 50 }, (_, index) => ({
      id: `source-${index}`, name: `素材-${index}.csv`, kind: 'table' as const,
      kindV1: 'material-data' as const, productName: '产品甲', attribution: '自有数据',
      text: `素材ID,卖点排序,需求场景\nm${index},Top1：安装方便,周末在家安装`
    })))
    expect(many).toHaveLength(50)
    expect(new Set(many.map((row) => row.materialKey)).size).toBe(50)
    expect(selectMaterialInsightScope(many, []).rows).toHaveLength(50)
  })

  it('keeps scene selection bound to the need-scene column and rejects competitor-as-verified', () => {
    const rows = readMaterialInsightRows(sources)
    const catalog = buildSceneCatalog(rows)
    expect(catalog.map((item) => item.text)).toContain('下班回家安装')
    const own = catalog.find((item) => item.text === '下班回家安装')!
    expect(validateSceneSelection(`TOP1\n真实场景：下班回家安装\n场景状态：已验证\n场景依据：需求场景｜${own.id}`, catalog)).toEqual([])
    expect(validateSceneSelection('TOP1\n真实场景：凭空想象的场景\n场景依据：VOC', catalog)).toHaveLength(1)
    const competitor = buildSceneCatalog([{ ...rows[3], attribution: '竞品数据' }])[0]
    expect(validateSceneSelection(`TOP1\n真实场景：办公室收货\n场景状态：已验证\n场景依据：需求场景｜${competitor.id}`, [competitor])).toContain('TOP1的竞品场景只能标记待测试。')
  })

  it('rejects incomplete global normalization maps', () => {
    expect(() => parseNormalizationReply(['安装方便', '便于安装'], '{"mappings":[{"raw":"安装方便","keyword":"安装方便"}]}')).toThrow(/覆盖/)
  })
})
