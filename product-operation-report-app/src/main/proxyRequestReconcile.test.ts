import { describe, expect, it, vi } from 'vitest'
import type { ProxyRequestState } from './proxyRequestLifecycle'
import { reconcileDetachedProxyTask } from './proxyRequestReconcile'

function state(overrides: Partial<ProxyRequestState> = {}): ProxyRequestState {
  return {
    requestId: '11111111-1111-4111-8111-111111111111',
    reportSessionId: 'report-a',
    taskKey: 'report-a:module:v2:product-info',
    taskType: 'module_product_info',
    model: 'gpt-5.5',
    attempt: 1,
    status: 'running',
    cancelRequested: false,
    upstreamSubmitted: true,
    usageSource: 'missing',
    startedAt: '2026-09-01T05:00:00Z',
    ...overrides
  }
}

const instantWait = (_ms: number, signal: AbortSignal): Promise<boolean> => Promise.resolve(!signal.aborted)

describe('detached proxy request reconciliation', () => {
  it('allows submission immediately when the server has no active request', async () => {
    const listActive = vi.fn().mockResolvedValue([])
    const cancel = vi.fn()
    const outcome = await reconcileDetachedProxyTask(
      'report-a:module:v2:product-info',
      new AbortController().signal,
      { listActive, cancel, wait: instantWait }
    )
    expect(outcome).toEqual({ status: 'ready', cancelledRequestIds: [], activeRequestIds: [] })
    expect(cancel).not.toHaveBeenCalled()
  })

  it('cancels a detached request and waits until the server proves it is terminal', async () => {
    const detached = state()
    const listActive = vi.fn()
      .mockResolvedValueOnce([detached])
      .mockResolvedValueOnce([state({ cancelRequested: true })])
      .mockResolvedValueOnce([])
    const cancel = vi.fn().mockResolvedValue(state({ cancelRequested: true }))

    const outcome = await reconcileDetachedProxyTask(
      detached.taskKey,
      new AbortController().signal,
      { listActive, cancel, wait: instantWait },
      [1, 1]
    )

    expect(cancel).toHaveBeenCalledTimes(1)
    expect(cancel).toHaveBeenCalledWith(detached.requestId)
    expect(outcome.status).toBe('ready')
    expect(outcome.cancelledRequestIds).toEqual([detached.requestId])
  })

  it('fails closed when request state cannot be confirmed', async () => {
    const outcome = await reconcileDetachedProxyTask(
      'report-a:module:v2:product-info',
      new AbortController().signal,
      {
        listActive: vi.fn().mockRejectedValue(new Error('network down')),
        cancel: vi.fn(),
        wait: instantWait
      }
    )
    expect(outcome.status).toBe('unavailable')
  })

  it('fails closed when active lookup returns a different logical task', async () => {
    const cancel = vi.fn()
    const outcome = await reconcileDetachedProxyTask(
      'report-a:module:v2:product-info',
      new AbortController().signal,
      {
        listActive: vi.fn().mockResolvedValue([state({ taskKey: 'report-a:module:v2:voc' })]),
        cancel,
        wait: instantWait
      }
    )
    expect(outcome.status).toBe('unavailable')
    expect(cancel).not.toHaveBeenCalled()
  })

  it('never allows a new attempt while the detached request remains running', async () => {
    const detached = state()
    const listActive = vi.fn().mockResolvedValue([detached])
    const cancel = vi.fn().mockResolvedValue(state({ cancelRequested: true }))
    const outcome = await reconcileDetachedProxyTask(
      detached.taskKey,
      new AbortController().signal,
      { listActive, cancel, wait: instantWait },
      [1, 1]
    )
    expect(outcome.status).toBe('pending')
    expect(outcome.activeRequestIds).toEqual([detached.requestId])
  })

  it('stops reconciliation without submitting anything after user abort', async () => {
    const controller = new AbortController()
    controller.abort()
    const listActive = vi.fn()
    const cancel = vi.fn()
    const outcome = await reconcileDetachedProxyTask(
      'report-a:module:v2:product-info',
      controller.signal,
      { listActive, cancel, wait: instantWait }
    )
    expect(outcome.status).toBe('stopped')
    expect(listActive).not.toHaveBeenCalled()
    expect(cancel).not.toHaveBeenCalled()
  })
})
