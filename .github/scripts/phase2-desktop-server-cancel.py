from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new)


ai_path = Path('product-operation-report-app/src/main/aiProxy.ts')
ai = ai_path.read_text(encoding='utf-8')
ai = replace_once(
    ai,
    "import { AI_PROXY_BASE_URL, AI_PROXY_HEALTH_URL, AI_PROXY_SESSION_URL, NETWORK_TIMEOUT_MS } from './serviceConfig'\n",
    """import { AI_PROXY_BASE_URL, AI_PROXY_HEALTH_URL, AI_PROXY_SESSION_URL, NETWORK_TIMEOUT_MS } from './serviceConfig'
import {
  assertSafeProxyRequestId,
  assertSafeProxyTaskKey,
  parseProxyRequestState,
  parseProxyRequestStates,
  type ProxyRequestState
} from './proxyRequestLifecycle'
""",
    'ai proxy lifecycle import',
)
ai = replace_once(
    ai,
    """export async function getAiProxyToken(force = false): Promise<string> {
  if (!force && cachedSession && cachedSession.expiresAt - Date.now() > 30_000) return cachedSession.token
  cachedSession = await createSession()
  return cachedSession.token
}

export function clearAiProxySession(): void {
""",
    """export async function getAiProxyToken(force = false): Promise<string> {
  if (!force && cachedSession && cachedSession.expiresAt - Date.now() > 30_000) return cachedSession.token
  cachedSession = await createSession()
  return cachedSession.token
}

type AuthorizedProxyRequestInit = Omit<RequestInit, 'headers'> & { headers?: Record<string, string> }

async function authorizedProxyJson(path: string, init: AuthorizedProxyRequestInit): Promise<Record<string, unknown>> {
  const request = async (forceSession: boolean): Promise<Record<string, unknown>> => {
    const token = await getAiProxyToken(forceSession)
    return jsonRequest(`${AI_PROXY_BASE_URL}${path}`, {
      ...init,
      headers: {
        accept: 'application/json',
        ...(init.headers || {}),
        authorization: `Bearer ${token}`
      }
    })
  }
  try {
    return await request(false)
  } catch (error) {
    if (!(error instanceof ProxyHttpError) || error.status !== 401) throw error
    clearAiProxySession()
    return request(true)
  }
}

export async function fetchProxyRequestState(requestId: string): Promise<ProxyRequestState> {
  const safeRequestId = assertSafeProxyRequestId(requestId)
  const body = await authorizedProxyJson(`/requests/${safeRequestId}`, { method: 'GET' })
  return parseProxyRequestState(body.request)
}

export async function fetchActiveProxyRequests(taskKey: string): Promise<ProxyRequestState[]> {
  const safeTaskKey = assertSafeProxyTaskKey(taskKey)
  // The server deliberately accepts only its SAFE_TEXT_RE alphabet here. Do not encode ':' into %3A.
  const body = await authorizedProxyJson(`/requests/active/${safeTaskKey}`, { method: 'GET' })
  return parseProxyRequestStates(body.requests)
}

export async function cancelProxyRequest(requestId: string): Promise<ProxyRequestState> {
  const safeRequestId = assertSafeProxyRequestId(requestId)
  const body = await authorizedProxyJson(`/requests/${safeRequestId}/cancel`, { method: 'POST' })
  return parseProxyRequestState(body.request)
}

export async function cancelProxyTask(taskKey: string, preferredRequestId?: string): Promise<ProxyRequestState[]> {
  const safeTaskKey = assertSafeProxyTaskKey(taskKey)
  if (preferredRequestId) {
    try {
      const preferred = await cancelProxyRequest(preferredRequestId)
      if (preferred.status === 'running') return [preferred]
    } catch (error) {
      if (!(error instanceof ProxyHttpError) || error.status !== 404) throw error
    }
  }
  const active = await fetchActiveProxyRequests(safeTaskKey)
  if (!active.length) return []
  return Promise.all(active.map((request) => cancelProxyRequest(request.requestId)))
}

export function clearAiProxySession(): void {
""",
    'authorized request lifecycle helpers',
)
ai_path.write_text(ai, encoding='utf-8')

index_path = Path('product-operation-report-app/src/main/index.ts')
index = index_path.read_text(encoding='utf-8')
index = replace_once(
    index,
    """  authorizeProxyProfiles,
  clearAiProxySession,
  clearProxyWalletSnapshot,
  fetchProxyWallet,
  testProxyHealth
} from './aiProxy'
""",
    """  authorizeProxyProfiles,
  cancelProxyTask,
  clearAiProxySession,
  clearProxyWalletSnapshot,
  fetchProxyWallet,
  testProxyHealth
} from './aiProxy'
import { ProxyRequestTracker, type TrackedProxyRequest } from './proxyRequestLifecycle'
""",
    'index proxy lifecycle imports',
)
index = replace_once(
    index,
    """  const finishClose = (): void => {
    cancelParsingForOwner(ownerId, '软件正在关闭，文件解析已停止。')
    chatRequests.abortOwner(ownerId)
""",
    """  const finishClose = (): void => {
    cancelParsingForOwner(ownerId, '软件正在关闭，文件解析已停止。')
    cancelProxyRequestsForOwner(ownerId)
    chatRequests.abortOwner(ownerId)
""",
    'close proxy cancellation',
)
index = replace_once(
    index,
    """  window.webContents.on('render-process-gone', () => {
    cancelParsingForOwner(ownerId, '界面已重新加载，旧文件解析已停止。')
    chatRequests.abortOwner(ownerId)
  })
""",
    """  window.webContents.on('render-process-gone', () => {
    cancelParsingForOwner(ownerId, '界面已重新加载，旧文件解析已停止。')
    cancelProxyRequestsForOwner(ownerId)
    chatRequests.abortOwner(ownerId)
  })
""",
    'render gone proxy cancellation',
)
index = replace_once(
    index,
    """  window.on('closed', () => {
    cancelParsingForOwner(ownerId, '窗口已关闭，旧文件解析已停止。')
    chatRequests.abortOwner(ownerId)
""",
    """  window.on('closed', () => {
    cancelParsingForOwner(ownerId, '窗口已关闭，旧文件解析已停止。')
    cancelProxyRequestsForOwner(ownerId)
    chatRequests.abortOwner(ownerId)
""",
    'closed proxy cancellation',
)
index = replace_once(
    index,
    """// ---- IPC：流式聊天 ----
const chatRequests = new ChatRequestRegistry(4)

ipcMain.on(
""",
    """// ---- IPC：流式聊天 ----
const chatRequests = new ChatRequestRegistry(4)
const proxyRequests = new ProxyRequestTracker()

function bestEffortCancelProxyRequest(request: TrackedProxyRequest): void {
  void cancelProxyTask(request.taskKey, request.currentRequestId).catch((error) => {
    console.error('Unable to propagate model cancellation to business server:', error)
  })
}

function cancelProxyRequestsForOwner(ownerId: number): void {
  for (const request of proxyRequests.drainOwner(ownerId)) bestEffortCancelProxyRequest(request)
}

function cancelAllProxyRequests(): void {
  for (const request of proxyRequests.drainAll()) bestEffortCancelProxyRequest(request)
}

ipcMain.on(
""",
    'proxy request tracker helpers',
)
index = replace_once(
    index,
    """    const controller = new AbortController()
    try {
      chatRequests.claim(id, event.sender.id, controller)
    } catch (error) {
      event.sender.send(channel, {
        type: 'error',
        message: error instanceof Error ? error.message : '模型任务暂时无法开始。',
        usage: emptyUsage(primaryProfile.model)
      })
      return
    }
""",
    """    const controller = new AbortController()
    try {
      chatRequests.claim(id, event.sender.id, controller)
      if (managedState.mode === 'proxy') proxyRequests.claim(id, event.sender.id, context.taskKey)
    } catch (error) {
      chatRequests.release(id, event.sender.id, controller)
      proxyRequests.release(id, event.sender.id)
      event.sender.send(channel, {
        type: 'error',
        message: error instanceof Error ? error.message : '模型任务暂时无法开始。',
        usage: emptyUsage(primaryProfile.model)
      })
      return
    }
""",
    'claim proxy request tracker',
)
index = replace_once(
    index,
    """      const sequence = await runModelFallbackSequence(profiles, async (profile, profileIndex) => {
        const attemptRequestId = profileIndex === 0 ? id : `${id}:fallback:${profileIndex}`
        const startedAt = new Date().toISOString()
""",
    """      const sequence = await runModelFallbackSequence(profiles, async (profile, profileIndex) => {
        if (controller.signal.aborted) {
          return {
            terminal: { type: 'error', message: '已停止', usage: emptyUsage(profile.model) },
            failureKind: 'aborted',
            outputChars: 0,
            hasVisibleOutput: false,
            aborted: true
          }
        }
        const attemptRequestId = profileIndex === 0 ? id : `${id}:fallback:${profileIndex}`
        if (managedState.mode === 'proxy') proxyRequests.setCurrent(id, event.sender.id, attemptRequestId)
        const startedAt = new Date().toISOString()
""",
    'prevent fallback after abort and track concrete request',
)
index = replace_once(
    index,
    """    } finally {
      chatRequests.release(id, event.sender.id, controller)
    }
  }
)

ipcMain.on('chat:abort', (event, id: string) => {
  if (typeof id === 'string') chatRequests.abort(id, event.sender.id)
})
""",
    """    } finally {
      proxyRequests.release(id, event.sender.id)
      chatRequests.release(id, event.sender.id, controller)
    }
  }
)

ipcMain.on('chat:abort', (event, id: string) => {
  if (typeof id !== 'string') return
  const tracked = proxyRequests.get(id, event.sender.id)
  chatRequests.abort(id, event.sender.id)
  if (tracked) bestEffortCancelProxyRequest(tracked)
})
""",
    'explicit abort propagation',
)
index = replace_once(
    index,
    """app.on('before-quit', () => {
  armHardExitWatchdog()
  chatRequests.abortAll()
  disposeParseService()
})
""",
    """app.on('before-quit', () => {
  armHardExitWatchdog()
  cancelAllProxyRequests()
  chatRequests.abortAll()
  disposeParseService()
})
""",
    'before quit proxy cancellation',
)
index_path.write_text(index, encoding='utf-8')
