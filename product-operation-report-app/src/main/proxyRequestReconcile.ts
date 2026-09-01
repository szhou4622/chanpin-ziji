import type { ProxyRequestState } from './proxyRequestLifecycle'

export type ProxyReconcileStatus = 'ready' | 'stopped' | 'pending' | 'unavailable'

export interface ProxyReconcileOutcome {
  status: ProxyReconcileStatus
  cancelledRequestIds: string[]
  activeRequestIds: string[]
}

export interface ProxyReconcilePort {
  listActive: (taskKey: string) => Promise<ProxyRequestState[]>
  cancel: (requestId: string) => Promise<ProxyRequestState>
  wait?: (ms: number, signal: AbortSignal) => Promise<boolean>
}

const DEFAULT_POLL_DELAYS_MS = [250, 500, 1_000, 1_500, 2_000, 2_500] as const

async function waitWithSignal(ms: number, signal: AbortSignal): Promise<boolean> {
  if (signal.aborted) return false
  return new Promise<boolean>((resolve) => {
    let settled = false
    const finish = (value: boolean): void => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      signal.removeEventListener('abort', onAbort)
      resolve(value)
    }
    const onAbort = (): void => finish(false)
    const timer = setTimeout(() => finish(true), ms)
    signal.addEventListener('abort', onAbort, { once: true })
  })
}

function runningForTask(states: ProxyRequestState[], taskKey: string): ProxyRequestState[] {
  return states.filter((request) => request.taskKey === taskKey && request.status === 'running')
}

/**
 * Reconcile a logical managed-proxy task before a new upstream submission.
 *
 * A prior transport failure can leave a server request running after the desktop
 * has lost its stream. Because the server intentionally does not persist model
 * output, such a detached request cannot be reattached safely. We therefore
 * request cancellation, wait until the server no longer reports it as running,
 * and only then allow the caller to submit a new attempt.
 *
 * Any inability to prove the prior request is gone fails closed. This protects
 * against overlapping nonterminal attempts and duplicate provider spend.
 */
export async function reconcileDetachedProxyTask(
  taskKey: string,
  signal: AbortSignal,
  port: ProxyReconcilePort,
  pollDelaysMs: readonly number[] = DEFAULT_POLL_DELAYS_MS
): Promise<ProxyReconcileOutcome> {
  const cancelled = new Set<string>()
  const wait = port.wait || waitWithSignal

  if (signal.aborted) return { status: 'stopped', cancelledRequestIds: [], activeRequestIds: [] }

  let active: ProxyRequestState[]
  try {
    active = runningForTask(await port.listActive(taskKey), taskKey)
  } catch {
    return { status: 'unavailable', cancelledRequestIds: [], activeRequestIds: [] }
  }
  if (!active.length) return { status: 'ready', cancelledRequestIds: [], activeRequestIds: [] }

  const requestCancel = async (request: ProxyRequestState): Promise<boolean> => {
    if (request.cancelRequested || cancelled.has(request.requestId)) return true
    try {
      await port.cancel(request.requestId)
      cancelled.add(request.requestId)
      return true
    } catch {
      return false
    }
  }

  for (const request of active) {
    if (signal.aborted) {
      return {
        status: 'stopped',
        cancelledRequestIds: [...cancelled],
        activeRequestIds: active.map((item) => item.requestId)
      }
    }
    if (!(await requestCancel(request))) {
      return {
        status: 'unavailable',
        cancelledRequestIds: [...cancelled],
        activeRequestIds: active.map((item) => item.requestId)
      }
    }
  }

  for (const delay of pollDelaysMs) {
    if (!(await wait(Math.max(0, delay), signal))) {
      return {
        status: 'stopped',
        cancelledRequestIds: [...cancelled],
        activeRequestIds: active.map((item) => item.requestId)
      }
    }
    try {
      active = runningForTask(await port.listActive(taskKey), taskKey)
    } catch {
      return {
        status: 'unavailable',
        cancelledRequestIds: [...cancelled],
        activeRequestIds: active.map((item) => item.requestId)
      }
    }
    if (!active.length) {
      return { status: 'ready', cancelledRequestIds: [...cancelled], activeRequestIds: [] }
    }
    for (const request of active) {
      if (!(await requestCancel(request))) {
        return {
          status: 'unavailable',
          cancelledRequestIds: [...cancelled],
          activeRequestIds: active.map((item) => item.requestId)
        }
      }
    }
  }

  return {
    status: 'pending',
    cancelledRequestIds: [...cancelled],
    activeRequestIds: active.map((item) => item.requestId)
  }
}
