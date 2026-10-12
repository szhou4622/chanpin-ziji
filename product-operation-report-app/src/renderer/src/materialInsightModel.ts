import type { ChatMessage, MaterialSellingPointEvidence } from '../../shared/types'
import type { MaterialDescription } from './materialInsights'

const EXTRACTION_BATCH_CHARS = 18_000
const NORMALIZATION_BATCH_CHARS = 20_000

export interface ExtractionInput {
  id: string
  text: string
  originalText: string
}

export interface ExtractionJob {
  id: string
  inputs: ExtractionInput[]
}

export interface ExtractedPhrase {
  inputId: string
  phrase: string
  evidence: string
}

function splitLongDescription(value: string, maxChars: number): string[] {
  if (value.length <= maxChars) return [value]
  const parts: string[] = []
  for (let start = 0; start < value.length; start += maxChars - 80) {
    parts.push(value.slice(start, start + maxChars))
  }
  return parts
}

export function buildExtractionJobs(descriptions: MaterialDescription[]): ExtractionJob[] {
  const unique = [...new Set(descriptions.map((description) => description.rawDescription.trim()).filter(Boolean))]
  const inputs = unique.flatMap((raw, index) => splitLongDescription(raw, 12_000).map((part, partIndex) => ({
    id: `D${index + 1}${partIndex ? `P${partIndex + 1}` : ''}`,
    text: part,
    originalText: raw
  })))
  const jobs: ExtractionJob[] = []
  let current: ExtractionInput[] = []
  let size = 0
  const flush = (): void => {
    if (!current.length) return
    jobs.push({ id: `extract-${String(jobs.length + 1).padStart(4, '0')}`, inputs: current })
    current = []
    size = 0
  }
  inputs.forEach((input) => {
    const next = input.text.length + input.id.length + 50
    if (current.length && size + next > EXTRACTION_BATCH_CHARS) flush()
    current.push(input)
    size += next
  })
  flush()
  return jobs
}

export function extractionMessages(job: ExtractionJob): ChatMessage[] {
  return [
    {
      role: 'system',
      content: [
        '你只分析本次提供的「卖点排序」原文，不参考标题、脚本、类目常识或其他资料。',
        '对每个输入ID识别独立且真实表达购买理由的产品属性、功能利益、体验、工艺、信任、服务、效率或价格权益短语。',
        '删除“突出/强调/展示/采用/对比展示”等策略修饰，只保留原文实际表达的产品价值；纯策略标签返回空数组。',
        '可从同一描述提取多个独立卖点，但不要机械拆词、不要同时给出同义宽泛词和具体词。保留否定、数值、单位、承诺强度及适用条件。',
        '必须对每个输入ID返回一项，包括没有有效卖点的项。只输出JSON：{"items":[{"id":"输入ID","phrases":[{"phrase":"候选短语","evidence":"原文连续片段"}]}]}。',
        'evidence必须原样截取自对应输入文本；不得编造、不得输出解释或Markdown。'
      ].join('\n')
    },
    {
      role: 'user',
      content: JSON.stringify(job.inputs.map(({ id, text }) => ({ id, text })))
    }
  ]
}

function parseJson(text: string): unknown {
  const trimmed = text.trim().replace(/^```(?:json)?\s*/iu, '').replace(/\s*```$/u, '')
  return JSON.parse(trimmed) as unknown
}

export function parseExtractionReply(job: ExtractionJob, text: string): ExtractedPhrase[] {
  const parsed = parseJson(text)
  if (!parsed || typeof parsed !== 'object' || !('items' in parsed) || !Array.isArray(parsed.items)) throw new Error('卖点提取结果不是有效JSON列表。')
  const expected = new Map(job.inputs.map((input) => [input.id, input]))
  const seen = new Set<string>()
  const result: ExtractedPhrase[] = []
  for (const item of parsed.items) {
    if (!item || typeof item !== 'object' || typeof item.id !== 'string' || !expected.has(item.id) || seen.has(item.id) || !Array.isArray(item.phrases)) {
      throw new Error('卖点提取覆盖ID缺失、重复或包含未知ID。')
    }
    seen.add(item.id)
    const original = expected.get(item.id)!.text
    for (const raw of item.phrases) {
      if (!raw || typeof raw.phrase !== 'string' || typeof raw.evidence !== 'string') throw new Error('卖点提取缺少候选短语或证据片段。')
      const phrase = raw.phrase.trim()
      const evidence = raw.evidence.trim()
      if (!phrase || phrase.length > 100 || !evidence || !original.includes(evidence)) throw new Error('卖点短语或证据片段不能反查原文。')
      result.push({ inputId: item.id, phrase, evidence })
    }
  }
  if (seen.size !== expected.size) throw new Error(`卖点提取只覆盖 ${seen.size}/${expected.size} 条描述。`)
  return result
}

export function expandExtractedPhrases(
  descriptions: MaterialDescription[],
  jobs: ExtractionJob[],
  extracted: ExtractedPhrase[]
): MaterialSellingPointEvidence[] {
  const byOriginal = new Map<string, ExtractedPhrase[]>()
  const originalById = new Map(jobs.flatMap((job) => job.inputs.map((input) => [input.id, input.originalText] as const)))
  extracted.forEach((item) => {
    const original = originalById.get(item.inputId)
    if (!original) throw new Error('卖点证据ID不能映射到原始描述。')
    byOriginal.set(original, [...(byOriginal.get(original) || []), item])
  })
  return descriptions.flatMap((description) => {
    const dedup = new Set<string>()
    return (byOriginal.get(description.rawDescription.trim()) || []).flatMap((item) => {
      const key = `${item.phrase}|${item.evidence}`
      if (dedup.has(key)) return []
      dedup.add(key)
      return [{
        sourceId: description.row.sourceId,
        sourceName: description.row.sourceName,
        sheetName: description.row.sheetName,
        rowEvidenceId: description.row.rowEvidenceId,
        materialKey: description.row.materialKey,
        topRank: description.topRank,
        rawDescription: description.rawDescription,
        evidenceSnippet: item.evidence,
        candidate: item.phrase
      }]
    })
  })
}

export function buildNormalizationJobs(phrases: string[]): string[][] {
  const sorted = [...new Set(phrases.map((phrase) => phrase.trim()).filter(Boolean))].sort((a, b) => a < b ? -1 : a > b ? 1 : 0)
  const batches: string[][] = []
  let current: string[] = []
  let size = 0
  sorted.forEach((phrase) => {
    if (current.length && size + phrase.length + 30 > NORMALIZATION_BATCH_CHARS) {
      batches.push(current)
      current = []
      size = 0
    }
    current.push(phrase)
    size += phrase.length + 30
  })
  if (current.length) batches.push(current)
  return batches
}

export function normalizationMessages(phrases: string[]): ChatMessage[] {
  return [
    {
      role: 'system',
      content: [
        '对本次报告候选卖点做同义归一；不使用固定品牌/产品词库，不补充原文没有的产品事实。',
        '只合并语义等价且条件、否定、数值及承诺强度无实质差异的表达。相关但不同的卖点保持分开；不确定时保持原词。',
        '标准名称优先使用输入中的清晰短语，或不增加新含义的简短概括；不要归成“品质好/效果好/性价比高”等宽泛概念。',
        '每个输入短语必须恰好返回一次。只输出JSON：{"mappings":[{"raw":"原短语","keyword":"标准卖点"}]}。'
      ].join('\n')
    },
    { role: 'user', content: JSON.stringify(phrases) }
  ]
}

export function parseNormalizationReply(phrases: string[], text: string): Record<string, string> {
  const parsed = parseJson(text)
  if (!parsed || typeof parsed !== 'object' || !('mappings' in parsed) || !Array.isArray(parsed.mappings)) throw new Error('同义归一结果不是有效JSON列表。')
  const expected = new Set(phrases)
  const result: Record<string, string> = {}
  for (const item of parsed.mappings) {
    if (!item || typeof item.raw !== 'string' || typeof item.keyword !== 'string' || !expected.has(item.raw) || Object.prototype.hasOwnProperty.call(result, item.raw)) {
      throw new Error('同义归一缺词、重复或包含未知表达。')
    }
    const keyword = item.keyword.trim()
    if (!keyword || keyword.length > 100 || /^(?:未知|无有效卖点|解析失败|暂无)$/u.test(keyword)) throw new Error('同义归一返回无效卖点。')
    result[item.raw] = keyword
  }
  if (Object.keys(result).length !== expected.size) throw new Error(`同义归一只覆盖 ${Object.keys(result).length}/${expected.size} 个候选词。`)
  return result
}
