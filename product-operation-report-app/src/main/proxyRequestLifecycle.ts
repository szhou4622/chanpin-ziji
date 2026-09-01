const REQUEST_ID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}(?::fallback:[1-3])?$/i
const TASK_KEY_RE = /^[A-Za-z0-9_.:-]{1,200}$/

export interface ProxyRequestState {
  requestId: string
  reportSessionId: string
  taskKey: string
  taskType: string
  model: string
  attempt: number
  status: string
  cancelRequested: boolean
  upstreamSubmitted: boolean
  usageSource: string
  startedAt: string
  endedAt?: string
}

export interface TrackedProxyRequest {
  rootRequestId: string
  ownerId: number
  taskKey: string
  currentRequestId?: string
}

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('业务服务器返回了无法识别的请求状态。')
  }
  return value as Record<string, unknown>
}

export function assertSafeProxyTaskKey(value: string): string {
  const candidate = value.trim()
  if (!TASK_KEY_RE.test(candidate)) throw new Error('模型任务标识无效。')
  return candidate
}

export function assertSafeProxyRequestId(value: string): string {
  const candidate = value.trim()
  if (!REQUEST_ID_RE.test(candidate)) throw new Error('模型请求标识无效。')
  return candidate
}

export function parseProxyRequestState(value: unknown): ProxyRequestState {
  const row = record(value)
  const requestId = assertSafeProxyRequestId(typeof row.requestId === 'string' ? row.requestId : '')
  const taskKey = assertSafeProxyTaskKey(typeof row.taskKey === 'string' ? row.taskKey : '')
  const reportSessionId = typeof row.reportSessionId === 'string' ? row.reportSessionId.slice(0, 200) : ''
  const taskType = typeof row.taskType === 'string' ? row.taskType.slice(0, 80) : ''
  const model = typeof row.model === 'string' ? row.model.slice(0, 200) : ''
  const status = typeof row.status === 'string' ? row.status.slice(0, 80) : ''
  const usageSource = typeof row.usageSource === 'string' ? row.usageSource.slice(0, 40) : ''
  const startedAt = typeof row.startedAt === 'string' ? row.startedAt.slice(0, 80) : ''
  const endedAt = typeof row.endedAt === 'string' && row.endedAt ? row.endedAt.slice(0, 80) : undefined
  const attempt = Number(row.attempt)
  if (!reportSessionId || !taskType || !model || !status || !startedAt || !Number.isInteger(attempt) || attempt < 1 || attempt > 100) {
    throw new Error('业务服务器返回了不完整的请求状态。')
  }
  return {
    requestId,
    reportSessionId,
    taskKey,
    taskType,
    model,
    attempt,
    status,
    cancelRequested: row.cancelRequested === true,
    upstreamSubmitted: row.upstreamSubmitted === true,
    usageSource,
    startedAt,
    ...(endedAt ? { endedAt } : {})
  }
}

export function parseProxyRequestStates(value: unknown): ProxyRequestState[] {
  if (!Array.isArray(value)) throw new Error('业务服务器返回了无法识别的请求列表。')
  return value.map(parseProxyRequestState).slice(0, 8)
}

export class ProxyRequestTracker {
  private readonly entries = new Map<string, TrackedProxyRequest>()

  claim(rootRequestId: string, ownerId: number, taskKey: string): void {
    const root = assertSafeProxyRequestId(rootRequestId)
    const safeTaskKey = assertSafeProxyTaskKey(taskKey)
    if (this.entries.has(root)) throw new Error('检测到重复的代理请求跟踪记录。')
    if (this.findByTaskKey(safeTaskKey)) throw new Error('同一模型任务正在处理中，请稍后重试。')
    this.entries.set(root, { rootRequestId: root, ownerId, taskKey: safeTaskKey })
  }

  findByTaskKey(taskKey: string, excludeRootRequestId?: string): TrackedProxyRequest | undefined {
    const safeTaskKey = assertSafeProxyTaskKey(taskKey)
    let exclude = ''
    if (excludeRootRequestId) {
      try {
        exclude = assertSafeProxyRequestId(excludeRootRequestId)
      } catch {
        exclude = ''
      }
    }
    for (const [root, entry] of this.entries) {
      if (root === exclude || entry.taskKey !== safeTaskKey) continue
      return { ...entry }
    }
    return undefined
  }

  setCurrent(rootRequestId: string, ownerId: number, requestId: string): boolean {
    const root = assertSafeProxyRequestId(rootRequestId)
    const current = assertSafeProxyRequestId(requestId)
    const entry = this.entries.get(root)
    if (!entry || entry.ownerId !== ownerId) return false
    entry.currentRequestId = current
    return true
  }

  get(rootRequestId: string, ownerId: number): TrackedProxyRequest | undefined {
    let root: string
    try {
      root = assertSafeProxyRequestId(rootRequestId)
    } catch {
      return undefined
    }
    const entry = this.entries.get(root)
    return entry && entry.ownerId === ownerId ? { ...entry } : undefined
  }

  release(rootRequestId: string, ownerId: number): boolean {
    const entry = this.get(rootRequestId, ownerId)
    return entry ? this.entries.delete(entry.rootRequestId) : false
  }

  drainOwner(ownerId: number): TrackedProxyRequest[] {
    const drained: TrackedProxyRequest[] = []
    for (const [root, entry] of this.entries) {
      if (entry.ownerId !== ownerId) continue
      drained.push({ ...entry })
      this.entries.delete(root)
    }
    return drained
  }

  drainAll(): TrackedProxyRequest[] {
    const drained = [...this.entries.values()].map((entry) => ({ ...entry }))
    this.entries.clear()
    return drained
  }

  get size(): number {
    return this.entries.size
  }
}
