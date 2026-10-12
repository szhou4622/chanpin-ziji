import type { ChatMessage, MaterialSellingPointInsight, ProjectTaskSnapshot } from '../../shared/types'
import { runModelRetry } from './store/analysis'
import { billingProof, confirmSavedResult, rejectIncompleteResult } from './store/billing'
import { fingerprintModuleMessages } from './modules'
import {
  buildExtractionJobs,
  buildNormalizationJobs,
  expandExtractedPhrases,
  extractionMessages,
  normalizationMessages,
  parseExtractionReply,
  parseNormalizationReply,
  type ExtractedPhrase,
  type ExtractionJob
} from './materialInsightModel'
import {
  computeSellingPointInsight,
  materialInsightFingerprint,
  parseSellingPointDescriptions,
  type MaterialInsightRow
} from './materialInsights'

export function materialInsightTaskPrefix(sessionId: string, fingerprint: string): string {
  return `${sessionId}:material-insight:v1:${fingerprint}`
}

function decodeInsight(text: string, fingerprint: string): MaterialSellingPointInsight | null {
  try {
    const result = JSON.parse(text) as MaterialSellingPointInsight
    if (result.version !== 1 || result.fingerprint !== fingerprint || !Array.isArray(result.items) || !Array.isArray(result.mappings)) return null
    const byKeyword = new Map<string, MaterialSellingPointInsight['mappings']>()
    result.mappings.forEach((mapping) => byKeyword.set(mapping.keyword, [...(byKeyword.get(mapping.keyword) || []), mapping]))
    return { ...result, items: result.items.map((item) => ({ ...item, evidence: byKeyword.get(item.keyword) || [] })) }
  } catch { return null }
}

export function readMaterialInsightResult(
  journal: Record<string, ProjectTaskSnapshot>,
  sessionId: string,
  fingerprint: string
): MaterialSellingPointInsight | null {
  const entry = journal[`${materialInsightTaskPrefix(sessionId, fingerprint)}:final`]
  if (entry?.status !== 'complete' || !entry.output) return null
  return decodeInsight(entry.output, fingerprint)
}

export async function runMaterialInsightWorkflow(params: {
  rows: MaterialInsightRow[]
  selectedProducts: string[]
  scopeLabel: string
  sessionId: string
  sourceCount: number
  imageCount: number
  getTask: (id: string) => ProjectTaskSnapshot | undefined
  saveTask: (id: string, task: ProjectTaskSnapshot) => Promise<void>
  setAbort: (fn: (() => void) | null) => void
  onProgress: (message: string) => void
}): Promise<MaterialSellingPointInsight> {
  const fingerprint = materialInsightFingerprint(params.rows, params.selectedProducts)
  const prefix = materialInsightTaskPrefix(params.sessionId, fingerprint)
  const finalId = `${prefix}:final`
  const previousFinal = params.getTask(finalId)
  if (previousFinal?.status === 'complete' && previousFinal.output) {
    const parsed = decodeInsight(previousFinal.output, fingerprint)
    if (parsed) return parsed
  }
  const descriptions = params.rows.flatMap(parseSellingPointDescriptions)
  const extractionJobs = buildExtractionJobs(descriptions)
  const aborters = new Map<string, () => void>()
  let stopRequested = false
  const setTaskAbort = (id: string, fn: (() => void) | null): void => {
    if (fn) aborters.set(id, fn)
    else aborters.delete(id)
    params.setAbort(aborters.size ? () => {
      stopRequested = true
      for (const abort of aborters.values()) abort()
    } : null)
  }
  const runLimited = async <T>(jobs: T[], worker: (job: T, index: number) => Promise<void>): Promise<void> => {
    let cursor = 0
    let failure: unknown
    await Promise.all(Array.from({ length: Math.min(2, jobs.length) }, async () => {
      while (!failure && !stopRequested && cursor < jobs.length) {
        const index = cursor++
        try { await worker(jobs[index], index) } catch (error) { failure = error }
      }
    }))
    if (failure) throw failure
    if (stopRequested) throw new Error('已停止')
  }
  const call = async (id: string, messages: ChatMessage[], validate: (text: string) => unknown): Promise<string> => {
    const inputFingerprint = fingerprintModuleMessages(messages)
    const saved = params.getTask(id)
    if (saved?.status === 'complete' && saved.inputFingerprint === inputFingerprint && saved.output) {
      try { validate(saved.output); return saved.output } catch { /* Retry only this invalid task. */ }
    }
    const result = await runModelRetry(messages, () => {}, (fn) => setTaskAbort(id, fn), undefined, 0, {
      reportSessionId: params.sessionId,
      taskType: 'module_selling_points',
      taskKey: id,
      billingRequestId: id,
      isVision: false,
      sourceCount: params.sourceCount,
      imageCount: params.imageCount,
      stepId: 'material-selling-cloud'
    })
    if (!result.ok || !result.text.trim()) {
      const error = result.error || '模型没有返回内容'
      await params.saveTask(id, { kind: 'module', status: 'failed', inputFingerprint, updatedAt: new Date().toISOString() })
      throw new Error(error)
    }
    try { validate(result.text) } catch (error) {
      await rejectIncompleteResult(id, result)
      await params.saveTask(id, { kind: 'module', status: 'failed', inputFingerprint, updatedAt: new Date().toISOString() })
      throw error
    }
    const completedTask = { kind: 'module' as const, status: 'complete' as const,
      output: result.text, inputFingerprint, ...billingProof(result), updatedAt: new Date().toISOString() }
    await params.saveTask(id, completedTask)
    const billingResult = await confirmSavedResult(id, result, result.text)
    if (billingResult.state === 'charged') {
      await params.saveTask(id, { ...completedTask, billingConfirmed: true })
    }
    return result.text
  }

  const extracted: ExtractedPhrase[] = []
  await runLimited(extractionJobs, async (job: ExtractionJob, index) => {
    if (index === 0 || (index + 1) % 5 === 0 || index === extractionJobs.length - 1) {
      params.onProgress(`正在提取素材卖点 ${index + 1}/${extractionJobs.length}`)
    }
    const text = await call(`${prefix}:${job.id}`, extractionMessages(job), (value) => parseExtractionReply(job, value))
    extracted.push(...parseExtractionReply(job, text))
  })
  const candidates = expandExtractedPhrases(descriptions, extractionJobs, extracted)
  const uniqueCandidates = [...new Set(candidates.map((item) => item.candidate))]
  let current = uniqueCandidates
  let normalization: Record<string, string> = Object.fromEntries(uniqueCandidates.map((item) => [item, item]))
  for (let pass = 0; current.length; pass++) {
    const jobs = buildNormalizationJobs(current)
    if (pass >= 5) throw new Error('候选卖点过多，无法在安全上下文内完成全批次统一归一。')
    const stepMap: Record<string, string> = {}
    await runLimited(jobs, async (phrases, index) => {
      if (index === 0 || (index + 1) % 5 === 0 || index === jobs.length - 1) {
        params.onProgress(`正在全批次归一卖点 ${index + 1}/${jobs.length}`)
      }
      const output = await call(`${prefix}:normalize-${pass}-${index}`, normalizationMessages(phrases),
        (value) => parseNormalizationReply(phrases, value))
      Object.assign(stepMap, parseNormalizationReply(phrases, output))
    })
    normalization = Object.fromEntries(Object.entries(normalization).map(([raw, keyword]) => [raw, stepMap[keyword] || keyword]))
    if (jobs.length === 1) break
    const next = [...new Set(Object.values(stepMap))]
    if (next.length >= current.length && buildNormalizationJobs(next).length >= jobs.length) {
      throw new Error('候选卖点未能收敛为可统一核对的词表，未生成误导性词云。')
    }
    current = next
  }
  const insight = computeSellingPointInsight({
    rows: params.rows,
    scopeLabel: params.scopeLabel,
    fingerprint,
    candidates,
    normalization
  })
  await params.saveTask(finalId, {
    kind: 'module', status: 'complete', output: JSON.stringify({
      ...insight, items: insight.items.map((item) => ({ ...item, evidence: [] }))
    }), inputFingerprint: fingerprint,
    updatedAt: new Date().toISOString()
  })
  return insight
}
