import type { ChatMessage, ModelTaskContext, SearchEvidence, SearchVerificationStatus } from '../../../shared/types'
import { buildFinalReportPartMessages, type PriorOutput } from '../sop'
import { FINAL_REPORT_PARTS } from '../reportTemplate'
import { validateFinalReportPart } from '../validate'
import { friendlyError } from './errors'
import { rejectIncompleteResult } from './billing'

export interface ModelRunResult {
  ok: boolean
  text: string
  requestId?: string
  outputSha256?: string
  error?: string
  searchStatus?: SearchVerificationStatus
  searchEvidence?: SearchEvidence[]
}

/** Five extra attempts after the first request, for six-module transient failures only. */
export const MODULE_TRANSIENT_RETRIES = 5

/** A distinct setter owns one sequential model/retry chain within a concurrent workflow. */
export function createModelAbortGroup(): {
  readonly aborted: boolean
  abort: () => void
  createSetter: () => (fn: (() => void) | null) => void
} {
  const active = new Set<() => void>()
  let aborted = false
  return {
    get aborted() { return aborted },
    abort: () => {
      aborted = true
      for (const abort of [...active]) {
        active.delete(abort)
        try { abort() } catch { /* One failed transport cannot prevent the others from stopping. */ }
      }
    },
    createSetter: () => {
      let current: (() => void) | null = null
      return (next) => {
        if (current) active.delete(current)
        current = next
        if (!next) return
        if (aborted) {
          current = null
          next()
        } else active.add(next)
      }
    }
  }
}

/** Only zero-output transient failures can be retried under the same logical task. */
export function shouldRetryTransientModelResult(result: ModelRunResult): boolean {
  if (result.ok || result.text.trim()) return false
  const error = result.error || ''
  if (/已停止|安全|内容过滤|积分不足|授权|403|401/i.test(error)) return false
  return /fetch failed|ECONNRESET|ETIMEDOUT|socket hang up|terminated|network|网络连接失败|模型线路连接失败|连接提前结束|服务繁忙|额度受限|429|HTTP\s*5\d\d|超时|没有返回内容|未生成内容|空响应|empty[_ -]?output|response stream was interrupted/i.test(error)
}

export function runModel(
  messages: ChatMessage[],
  onAcc: (acc: string) => void,
  setAbort: (fn: (() => void) | null) => void,
  context: ModelTaskContext
): Promise<ModelRunResult> {
  return new Promise((resolve) => {
    let acc = ''
    let settled = false
    let publishTimer: number | null = null
    let lastPublished = ''
    let searchStatus: SearchVerificationStatus | undefined
    const searchEvidence: SearchEvidence[] = []
    const seenSearchUrls = new Set<string>()
    const publish = (text: string): void => {
      if (text === lastPublished) return
      lastPublished = text
      onAcc(text)
    }
    const flush = (text = acc): void => {
      if (publishTimer !== null) {
        window.clearTimeout(publishTimer)
        publishTimer = null
      }
      publish(text)
    }
    const done = (result: ModelRunResult): void => {
      if (settled) return
      settled = true
      flush(result.text)
      setAbort(null)
      resolve(result)
    }
    try {
      const handle = window.api.sendChat(messages, context, {
        onChunk: (delta) => {
          if (settled) return
          acc += delta
          if (publishTimer === null) {
            publishTimer = window.setTimeout(() => {
              publishTimer = null
              publish(acc)
            }, 60)
          }
        },
        onSearchStatus: (status) => { searchStatus = status },
        onSearchEvidence: (evidence) => {
          if (seenSearchUrls.has(evidence.url)) return
          seenSearchUrls.add(evidence.url)
          searchEvidence.push(evidence)
        },
        onDone: (full, requestId, outputSha256) => done({
          ok: true, text: full || acc, requestId, outputSha256, searchStatus, searchEvidence
        }),
        onError: (message) => done({ ok: false, text: acc, error: friendlyError(message), searchStatus, searchEvidence })
      })
      if (!settled) setAbort(() => {
        try { handle.abort() } catch { /* Still finish locally if transport cleanup fails. */ }
        done({ ok: false, text: acc, error: '已停止', searchStatus, searchEvidence })
      })
    } catch (error) {
      done({ ok: false, text: acc, error: friendlyError(error), searchStatus, searchEvidence })
    }
  })
}

export async function runModelRetry(
  messages: ChatMessage[],
  onAcc: (acc: string) => void,
  setAbort: (fn: (() => void) | null) => void,
  onRetry?: (n: number) => void,
  retries = 1,
  taskContext?: Omit<ModelTaskContext, 'attempt'>
): Promise<ModelRunResult> {
  if (!taskContext) throw new Error('模型任务缺少必要标识。')
  let result = await runModel(messages, onAcc, setAbort, { ...taskContext, attempt: 1 })
  let retry = 0
  while (retry < retries && shouldRetryTransientModelResult(result)) {
    retry += 1
    onRetry?.(retry)
    const wait = result.error?.match(/等待\s*(\d+)\s*秒/)
    const schedule = [1_000, 3_000, 7_000]
    const delay = wait
      ? Math.min(60, Number(wait[1])) * 1000
      : schedule[Math.min(retry - 1, schedule.length - 1)] + Math.floor(Math.random() * 501)
    let stopped = false
    await new Promise<void>((resolve) => {
      const timer = window.setTimeout(resolve, delay)
      setAbort(() => {
        stopped = true
        window.clearTimeout(timer)
        resolve()
      })
    })
    setAbort(null)
    if (stopped) return { ok: false, text: '', error: '已停止' }
    result = await runModel(messages, onAcc, setAbort, { ...taskContext, attempt: retry + 1 })
  }
  return result
}

export async function runFinalReportInParts(params: {
  cleanedData: string
  priorOutputs: PriorOutput[]
  feedback: string
  setAbort: (fn: (() => void) | null) => void
  onProgress: (text: string) => void
  onRetry: (partLabel: string, n: number) => void
  taskContext: {
    reportSessionId: string
    taskType: 'final_part' | 'revision_part'
    taskKeyPrefix: string
    sourceCount: number
    imageCount: number
  }
  parts?: typeof FINAL_REPORT_PARTS
  completedParts?: Record<string, string>
  onPartComplete?: (taskId: string, text: string, result: ModelRunResult) => Promise<void>
}): Promise<ModelRunResult> {
  let full = ''
  for (const part of params.parts || FINAL_REPORT_PARTS) {
    const taskId = `${params.taskContext.taskKeyPrefix}:${part.id}`
    const completed = params.completedParts?.[taskId]?.trim()
    if (completed && !validateFinalReportPart(completed, part).length) {
      full = `${full}${completed}\n\n`
      params.onProgress(full)
      continue
    }
    let current = ''
    const result = await runModelRetry(
      buildFinalReportPartMessages({
        part,
        cleanedData: params.cleanedData,
        priorOutputs: params.priorOutputs,
        feedback: params.feedback
      }),
      (acc) => {
        current = acc
        params.onProgress(`${full}${acc}`)
      },
      params.setAbort,
      (n) => params.onRetry(part.label, n),
      1,
      {
        reportSessionId: params.taskContext.reportSessionId,
        taskType: params.taskContext.taskType,
        taskKey: taskId,
        billingRequestId: taskId,
        isVision: false,
        sourceCount: params.taskContext.sourceCount,
        imageCount: params.taskContext.imageCount,
        partId: part.id
      }
    )
    if (!result.ok) return { ok: false, text: full + current, error: result.error }
    const partText = result.text.trim()
    const errors = validateFinalReportPart(partText, part)
    if (errors.length) {
      await rejectIncompleteResult(taskId, result)
      return { ok: false, text: full + partText, error: `${part.label}结构检查未通过：${errors.join('；')}` }
    }
    await params.onPartComplete?.(taskId, partText, result)
    full = `${full}${partText}\n\n`
    params.onProgress(full)
  }
  return { ok: true, text: full.trim() }
}

const REVISION_PART_KEYWORDS: Record<(typeof FINAL_REPORT_PARTS)[number]['id'], RegExp> = {
  'part-0-4': /结论|数据来源|产品基础|一方数据|竞品|素材打法/u,
  'part-5-8': /卖点|人群|场景|内容主线/u,
  'part-9': /脚本|选题|3\s*秒|执行方向|视频分类|创作视角/u,
  'part-10-11': /经营建议|行动建议|限制|风险|近期|中期|验证项/u
}

function partForSection(section: number): (typeof FINAL_REPORT_PARTS)[number] | undefined {
  return FINAL_REPORT_PARTS.find((part) => part.sections.includes(String(section)))
}

export function selectRevisionParts(feedback: string): typeof FINAL_REPORT_PARTS {
  const selected = new Set<string>()
  for (const match of feedback.matchAll(/(?:第\s*)?(10|11|[0-9])\s*[-—至到]\s*(10|11|[0-9])\s*章/gu)) {
    for (let section = Math.min(Number(match[1]), Number(match[2])); section <= Math.max(Number(match[1]), Number(match[2])); section++) {
      const part = partForSection(section)
      if (part) selected.add(part.id)
    }
  }
  for (const match of feedback.matchAll(/(?:第\s*)?(10|11|[0-9])\s*章/gu)) {
    const part = partForSection(Number(match[1]))
    if (part) selected.add(part.id)
  }
  if (!selected.size) {
    for (const part of FINAL_REPORT_PARTS) if (REVISION_PART_KEYWORDS[part.id].test(feedback)) selected.add(part.id)
  }
  return selected.size ? FINAL_REPORT_PARTS.filter((part) => selected.has(part.id)) as typeof FINAL_REPORT_PARTS : FINAL_REPORT_PARTS
}

function sectionHeadingStart(markdown: string, section: string): number {
  const escaped = section.replace(/[.*+?^${}()|[\]\\]/gu, '\\$&')
  return new RegExp(`^##\\s*${escaped}(?:[.、：:\\s]|$)`, 'mu').exec(markdown)?.index ?? -1
}

function partBounds(markdown: string, part: (typeof FINAL_REPORT_PARTS)[number]): { start: number; end: number; text: string } | null {
  for (const section of part.sections) if (sectionHeadingStart(markdown, section) < 0) return null
  const start = part.id === 'part-0-4' ? 0 : sectionHeadingStart(markdown, part.sections[0])
  if (start < 0) return null
  const later = part.id === 'part-0-4' ? ['5', '9', '10'] : part.id === 'part-5-8' ? ['9', '10'] : part.id === 'part-9' ? ['10'] : []
  const ends = later.map((section) => sectionHeadingStart(markdown, section)).filter((index) => index > start)
  const end = ends.length ? Math.min(...ends) : markdown.length
  return { start, end, text: markdown.slice(start, end).trim() }
}

export function mergeRevisionParts(previousReport: string, generatedParts: string, selectedParts: typeof FINAL_REPORT_PARTS): string | null {
  let merged = previousReport
  const replacements = selectedParts.map((part) => ({ part, previous: partBounds(previousReport, part), replacement: partBounds(generatedParts, part)?.text || null }))
  if (replacements.some((item) => !item.previous || !item.replacement)) return null
  for (const item of replacements.map((entry) => ({ ...entry, start: entry.previous!.start, end: entry.previous!.end })).sort((a, b) => b.start - a.start)) {
    const after = merged.slice(item.end)
    merged = `${merged.slice(0, item.start)}${item.replacement!.trim()}${after && !item.replacement!.endsWith('\n\n') ? '\n\n' : ''}${after}`
  }
  return merged.trim()
}
