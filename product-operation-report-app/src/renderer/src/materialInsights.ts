import Papa from 'papaparse'
import type {
  MaterialSellingPointEvidence,
  MaterialSellingPointInsight,
  MaterialSellingPointMapping,
  ProjectSourceSnapshot,
  SceneCatalogEntry
} from '../../shared/types'
import { sourceEvidenceId, sourceEvidenceScope } from './sourceCleanBatches'
export type { SceneCatalogEntry } from '../../shared/types'

export const MATERIAL_INSIGHT_VERSION = 'material-insight-v2-own'
export const UNLABELED_PRODUCT = '未标注产品'

export interface MaterialInsightRow {
  sourceId: string
  sourceName: string
  sheetName: string
  rowEvidenceId: string
  materialKey: string
  product: string
  attribution: string
  platform: string
  sellingPoint: string
  needScene: string
}

export interface MaterialDescription {
  id: string
  row: MaterialInsightRow
  topRank: 1 | 2 | 3 | null
  rawDescription: string
}

export interface MaterialInsightScope {
  rows: MaterialInsightRow[]
  products: string[]
  selectedProducts: string[]
  label: string
  needsSelection: boolean
  error?: string
}

const parsedMaterialRows = new WeakMap<ProjectSourceSnapshot, Map<number, { rows: MaterialInsightRow[]; diagnostics: string[] }>>()

function normalizeHeader(value: string): string {
  return value.normalize('NFKC').replace(/[\s\uFEFF：:（）()\[\]]/gu, '').toLocaleLowerCase('zh-CN')
}

function headerIndex(headers: string[], pattern: RegExp): number {
  return headers.findIndex((header) => pattern.test(normalizeHeader(header)))
}

function workbookBlocks(text: string): Array<{ name: string; text: string }> {
  const marker = /^###\s*工作表：([^\r\n]+)\r?$/gmu
  const matches = [...text.matchAll(marker)]
  if (!matches.length) return [{ name: 'Sheet1', text }]
  return matches.map((match, index) => ({
    name: match[1].trim(),
    text: text.slice((match.index || 0) + match[0].length, matches[index + 1]?.index ?? text.length)
      .split(/^####\s*单元格补充证据/gmu)[0].trim()
  })).filter((block) => block.text)
}

function stableHash(value: string): string {
  let hash = 2166136261
  for (let index = 0; index < value.length; index++) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(16).padStart(8, '0')
}

function materialIdentity(
  source: ProjectSourceSnapshot,
  product: string,
  headers: string[],
  cells: string[],
  rowEvidenceId: string,
  sourceOrdinal: number
): string {
  const index = headerIndex(headers, /^(?:素材id|素材编号|视频id|视频编号|原视频链接|视频链接|素材链接)$/u)
  const raw = index >= 0 ? (cells[index] || '').trim() : ''
  if (!raw) return `record:${sourceOrdinal}:${rowEvidenceId}`
  const namespace = `${(source.platform || '').trim().toLocaleLowerCase('zh-CN')}|${product.toLocaleLowerCase('zh-CN')}|${source.attribution || ''}`
  return `material:${stableHash(`${namespace}|${raw}`)}`
}

function readMaterialRows(sources: ProjectSourceSnapshot[], diagnostics: string[], onlyOwn: boolean): MaterialInsightRow[] {
  const result: MaterialInsightRow[] = []
  for (const [sourceOrdinal, source] of sources.entries()) {
    if (onlyOwn && source.attribution !== '自有数据') continue
    if (source.kind !== 'table' || source.kindV1 !== 'material-data' || !source.text?.trim() || source.error) continue
    const cached = parsedMaterialRows.get(source)?.get(sourceOrdinal)
    if (cached) {
      result.push(...cached.rows)
      diagnostics.push(...cached.diagnostics)
      continue
    }
    const startIndex = result.length
    const sourceDiagnostics: string[] = []
    const scope = sourceEvidenceScope(source)
    let globalRow = 0
    for (const block of workbookBlocks(source.text)) {
      const parsed = Papa.parse<string[]>(block.text, { skipEmptyLines: 'greedy', dynamicTyping: false })
      if (parsed.errors.some((error) => error.type === 'Quotes')) {
        const message = `「${source.name}」的工作表「${block.name}」存在无法可靠解析的引号结构。`
        diagnostics.push(message)
        sourceDiagnostics.push(message)
        continue
      }
      const records = parsed.data.map((row) => row.map((cell) => String(cell ?? '').trim())).filter((row) => row.some(Boolean))
      if (records.length < 2) continue
      const headers = records[0]
      const sellingIndex = headerIndex(headers, /^卖点排序(?:top[1-3](?:[-~至到]?[1-3])?)?$/u)
      const sceneIndex = headerIndex(headers, /^需求场景$/u)
      const productIndex = headerIndex(headers, /^(?:产品|产品名称|商品名称)$/u)
      const evidenceIndex = headerIndex(headers, /^__证据id$/u)
      records.slice(1).forEach((cells) => {
        globalRow += 1
        const product = (productIndex >= 0 ? cells[productIndex] : '')?.trim() || source.productName?.trim() || UNLABELED_PRODUCT
        const rowEvidenceId = (evidenceIndex >= 0 ? cells[evidenceIndex] : '')?.trim() || sourceEvidenceId('R', scope, globalRow)
        result.push({
          sourceId: source.id,
          sourceName: source.name,
          sheetName: block.name,
          rowEvidenceId,
          materialKey: materialIdentity(source, product, headers, cells, rowEvidenceId, sourceOrdinal),
          product,
          attribution: source.attribution || '',
          platform: source.platform || '',
          sellingPoint: sellingIndex >= 0 ? cells[sellingIndex] || '' : '',
          needScene: sceneIndex >= 0 ? cells[sceneIndex] || '' : ''
        })
      })
    }
    const sourceCache = parsedMaterialRows.get(source) || new Map<number, { rows: MaterialInsightRow[]; diagnostics: string[] }>()
    sourceCache.set(sourceOrdinal, { rows: result.slice(startIndex), diagnostics: sourceDiagnostics })
    parsedMaterialRows.set(source, sourceCache)
  }
  return result
}

export function readMaterialInsightRows(sources: ProjectSourceSnapshot[], diagnostics: string[] = []): MaterialInsightRow[] {
  return readMaterialRows(sources, diagnostics, false)
}

export function readOwnMaterialInsightRows(sources: ProjectSourceSnapshot[], diagnostics: string[] = []): MaterialInsightRow[] {
  // Retain original source ordinals so evidence/material identities match the full report.
  return readMaterialRows(sources, diagnostics, true)
}

export function selectMaterialInsightScope(
  rows: MaterialInsightRow[],
  requestedProducts: string[]
): MaterialInsightScope {
  const products = [...new Set(rows.map((row) => row.product))]
    .sort((a, b) => a < b ? -1 : a > b ? 1 : 0)
  const selectedProducts = products.length <= 1 ? products : [...new Set(requestedProducts.map((name) => name.trim()).filter(Boolean))]
  if (products.length > 1 && products.includes(UNLABELED_PRODUCT)) {
    return { rows: [], products, selectedProducts, label: '', needsSelection: true,
      error: '素材含未标注产品的记录；请在来源表补齐产品名称，或在对应文件下填写产品归属。' }
  }
  const unknown = selectedProducts.filter((name) => !products.includes(name))
  if (unknown.length) return { rows: [], products, selectedProducts, label: '', needsSelection: true, error: `产品范围已变化，请重新选择：${unknown.join('、')}` }
  if (products.length > 1 && !selectedProducts.length) {
    return { rows: [], products, selectedProducts, label: '', needsSelection: true, error: '素材中有多个产品，请先明确选择本次分析范围。' }
  }
  const effective = selectedProducts.length ? selectedProducts : products
  const selected = new Set(effective)
  return {
    rows: rows.filter((row) => selected.has(row.product)),
    products,
    selectedProducts: effective,
    label: effective.length ? effective.join('、') : '本次上传素材',
    needsSelection: false
  }
}

/** The word cloud uses own material; the general scope remains available to scene analysis. */
export function selectOwnMaterialInsightScope(
  rows: MaterialInsightRow[],
  requestedProducts: string[]
): MaterialInsightScope {
  const ownProducts = new Set(rows.filter((row) => row.attribution === '自有数据').map((row) => row.product))
  if (!ownProducts.size) {
    return { rows: [], products: [], selectedProducts: [], label: '自有素材', needsSelection: false }
  }
  const scope = selectMaterialInsightScope(rows, requestedProducts)
  const selectedProducts = scope.selectedProducts.filter((product) => ownProducts.has(product))
  return {
    ...scope,
    rows: scope.rows.filter((row) => row.attribution === '自有数据'),
    products: scope.products.filter((product) => ownProducts.has(product)),
    selectedProducts,
    label: selectedProducts.length ? selectedProducts.join('、') : '自有素材'
  }
}

export function parseSellingPointDescriptions(row: MaterialInsightRow): MaterialDescription[] {
  const raw = row.sellingPoint.trim()
  if (!raw) return []
  let structured: unknown
  if (/^[\[{]/u.test(raw)) {
    try { structured = JSON.parse(raw) } catch { /* Ordinary text may start with a bracket. */ }
  }
  const parts: Array<{ rank: 1 | 2 | 3 | null; value: string }> = []
  if (Array.isArray(structured)) {
    structured.slice(0, 3).forEach((value, index) => {
      if (typeof value === 'string' && value.trim()) parts.push({ rank: (index + 1) as 1 | 2 | 3, value: value.trim() })
    })
  } else if (structured && typeof structured === 'object') {
    Object.entries(structured).forEach(([key, value]) => {
      const hit = key.match(/^(?:top)?\s*([1-3])$/iu)
      if (hit && typeof value === 'string' && value.trim()) parts.push({ rank: Number(hit[1]) as 1 | 2 | 3, value: value.trim() })
    })
  }
  if (!parts.length) {
    const marker = /(?:^|[\r\n;；,，]|\s)(?:TOP\s*([1-9])|([1-9])\s*[.、)）])\s*[：:\-、.]?\s*/gimu
    const matches = [...raw.matchAll(marker)]
    if (matches.length) {
      matches.forEach((match, index) => {
        const rank = Number(match[1] || match[2])
        const value = raw.slice((match.index || 0) + match[0].length, matches[index + 1]?.index ?? raw.length).trim()
        if (rank >= 1 && rank <= 3 && value) parts.push({ rank: rank as 1 | 2 | 3, value })
      })
    } else parts.push({ rank: null, value: raw })
  }
  return parts.map((part, index) => ({
    id: `${row.rowEvidenceId}:${part.rank ?? 'U'}:${index + 1}`,
    row,
    topRank: part.rank,
    rawDescription: part.value
  }))
}

export function buildSceneCatalog(rows: MaterialInsightRow[]): SceneCatalogEntry[] {
  const grouped = new Map<string, { text: string; attribution: string; sources: SceneCatalogEntry['sources']; keys: Set<string> }>()
  rows.forEach((row) => {
    const value = row.needScene.replace(/\s+/gu, ' ').trim()
    if (!value || /^(?:无|未知|暂无|不适用|未填写|[-—/])$/u.test(value)) return
    const key = `${row.attribution}|${value}`
    const item = grouped.get(key) || { text: value, attribution: row.attribution, sources: [], keys: new Set<string>() }
    item.sources.push({ sourceName: row.sourceName, sheetName: row.sheetName, rowEvidenceId: row.rowEvidenceId, materialKey: row.materialKey })
    item.keys.add(row.materialKey)
    grouped.set(key, item)
  })
  return [...grouped.values()].map((item, index) => ({
    id: `SC-${stableHash(`${item.attribution}|${item.text}`)}-${String(index + 1).padStart(4, '0')}`,
    text: item.text,
    attribution: item.attribution,
    materialCount: item.keys.size,
    sources: item.sources
  })).sort((a, b) => b.materialCount - a.materialCount || (a.text < b.text ? -1 : a.text > b.text ? 1 : 0))
}

export function validateSceneSelection(output: string, catalog: SceneCatalogEntry[]): string[] {
  if (output.trim().startsWith('暂无分析')) return []
  const allowed = new Map(catalog.map((item) => [item.id.toUpperCase(), item]))
  const blocks = output.split(/^TOP\s*[1-5]\s*$/gimu).slice(1)
  if (!blocks.length) return ['M6缺少有效场景组合。']
  const errors: string[] = []
  blocks.forEach((block, index) => {
    const scene = block.match(/^真实场景\s*[：:]\s*(.+)$/mu)?.[1]?.trim() || ''
    const basis = block.match(/^场景依据\s*[：:]\s*(.+)$/mu)?.[1]?.trim() || ''
    const sceneId = basis.match(/SC-[a-f0-9]{8}-\d{4}/iu)?.[0]?.toUpperCase() || ''
    const entry = allowed.get(sceneId)
    if (!entry || !scene || scene !== entry.text) errors.push(`TOP${index + 1}的真实场景必须逐字对应“需求场景”证据ID。`)
    if (entry && /竞品/u.test(entry.attribution) && !/^场景状态\s*[：:]\s*待测试\s*$/mu.test(block)) {
      errors.push(`TOP${index + 1}的竞品场景只能标记待测试。`)
    }
  })
  return errors
}

export function materialInsightFingerprint(rows: MaterialInsightRow[], selectedProducts: string[]): string {
  const ownRows = rows.filter((row) => row.attribution === '自有数据')
  const products = selectedProducts.filter((product) => ownRows.some((row) => row.product === product))
  const input = `${MATERIAL_INSIGHT_VERSION}|${products.join('|')}|${ownRows.map((row) => [
    row.rowEvidenceId, row.materialKey, row.product, row.sellingPoint, row.needScene
  ].join('|')).join('\n')}`
  return `${stableHash(input)}-${input.length}-${ownRows.length}`
}

export function computeSellingPointInsight(input: {
  rows: MaterialInsightRow[]
  scopeLabel: string
  fingerprint: string
  candidates: MaterialSellingPointEvidence[]
  normalization: Record<string, string>
}): MaterialSellingPointInsight {
  const rows = input.rows.filter((row) => row.attribution === '自有数据')
  const evidenceKey = (row: Pick<MaterialInsightRow, 'sourceId' | 'rowEvidenceId' | 'materialKey'>): string =>
    JSON.stringify([row.sourceId, row.rowEvidenceId, row.materialKey])
  const allowedEvidence = new Set(rows.map(evidenceKey))
  const allMaterials = new Set(rows.map((row) => row.materialKey))
  const withSellingPoint = new Set(rows.filter((row) => row.sellingPoint.trim()).map((row) => row.materialKey))
  const missingSellingPointRows = rows.filter((row) => !withSellingPoint.has(row.materialKey))
    .map((row) => ({ sourceName: row.sourceName, sheetName: row.sheetName, rowEvidenceId: row.rowEvidenceId }))
  const mappings: MaterialSellingPointMapping[] = input.candidates.flatMap((candidate) => {
    if (!allowedEvidence.has(evidenceKey(candidate))) return []
    const keyword = input.normalization[candidate.candidate]?.trim()
    if (!keyword || /^(?:未知|无有效卖点|解析失败|暂无)$/u.test(keyword)) return []
    return [{ ...candidate, keyword }]
  })
  const grouped = new Map<string, MaterialSellingPointMapping[]>()
  mappings.forEach((mapping) => grouped.set(mapping.keyword, [...(grouped.get(mapping.keyword) || []), mapping]))
  const items = [...grouped.entries()].map(([keyword, evidence]) => {
    const byMaterial = new Map<string, 1 | 2 | 3 | null>()
    evidence.forEach((item) => {
      const current = byMaterial.get(item.materialKey)
      if (current === undefined || (item.topRank !== null && (current === null || item.topRank < current))) {
        byMaterial.set(item.materialKey, item.topRank)
      }
    })
    const ranks = [...byMaterial.values()]
    const top1Count = ranks.filter((rank) => rank === 1).length
    const top2Count = ranks.filter((rank) => rank === 2).length
    const top3Count = ranks.filter((rank) => rank === 3).length
    const unrankedCount = ranks.filter((rank) => rank === null).length
    const materialCount = byMaterial.size
    return {
      keyword, materialCount,
      coverageRate: allMaterials.size ? materialCount / allMaterials.size : 0,
      top1Count, top2Count, top3Count, unrankedCount,
      rankScore: top1Count * 3 + top2Count * 2 + top3Count,
      evidence
    }
  }).sort((a, b) => b.materialCount - a.materialCount || b.rankScore - a.rankScore || (a.keyword < b.keyword ? -1 : a.keyword > b.keyword ? 1 : 0))
  return {
    version: 1,
    sourceScope: 'own',
    fingerprint: input.fingerprint,
    scopeLabel: input.scopeLabel,
    totalMaterials: allMaterials.size,
    effectiveMaterials: new Set(mappings.map((mapping) => mapping.materialKey)).size,
    normalizedCount: items.length,
    missingSellingPointMaterials: allMaterials.size - withSellingPoint.size,
    missingSellingPointRows,
    items: items.slice(0, 20),
    mappings
  }
}
