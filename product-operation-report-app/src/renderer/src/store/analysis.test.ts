import { afterEach, describe, expect, it, vi } from 'vitest'
import { MODULE_TRANSIENT_RETRIES, createModelAbortGroup, runModel, runModelRetry, shouldRetryTransientModelResult } from './analysis'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('concurrent model cancellation', () => {
  const context = {
    reportSessionId: 'report-stop', taskType: 'module_product_info' as const, taskKey: 'task',
    billingRequestId: 'task', isVision: false, sourceCount: 1, imageCount: 0, attempt: 1
  }

  it('stops every remaining stream after another stream completes and releases finished handles', async () => {
    const callbacks: Array<Parameters<typeof window.api.sendChat>[2]> = []
    const aborters = [vi.fn(), vi.fn(() => { throw new Error('transport already gone') }), vi.fn()]
    vi.stubGlobal('window', { setTimeout, clearTimeout, api: {
      sendChat: (_messages: unknown, _context: unknown, handlers: Parameters<typeof window.api.sendChat>[2]) => {
        callbacks.push(handlers)
        return { abort: aborters[callbacks.length - 1] }
      }
    } })
    const group = createModelAbortGroup()
    const runs = aborters.map(() => runModel([], () => undefined, group.createSetter(), context))
    callbacks[0].onDone?.('complete')
    group.abort()
    const results = await Promise.all(runs)
    expect(results.map((result) => result.ok)).toEqual([true, false, false])
    expect(aborters[0]).not.toHaveBeenCalled()
    expect(aborters[1]).toHaveBeenCalledTimes(1)
    expect(aborters[2]).toHaveBeenCalledTimes(1)
    group.abort()
    expect(aborters[1]).toHaveBeenCalledTimes(1)
    expect(aborters[2]).toHaveBeenCalledTimes(1)
  })

  it('does not leave an abort handle when the bridge finishes synchronously', async () => {
    const abort = vi.fn()
    const setAbort = vi.fn()
    vi.stubGlobal('window', { setTimeout, clearTimeout, api: {
      sendChat: (_messages: unknown, _context: unknown, handlers: Parameters<typeof window.api.sendChat>[2]) => {
        handlers.onDone?.('complete')
        return { abort }
      }
    } })
    expect((await runModel([], () => undefined, setAbort, context)).ok).toBe(true)
    expect(setAbort).toHaveBeenLastCalledWith(null)
    expect(setAbort).toHaveBeenCalledTimes(1)
  })

  it('cancels another task retry backoff after a concurrent stream completes', async () => {
    vi.useFakeTimers()
    const callbacks: Array<Parameters<typeof window.api.sendChat>[2]> = []
    const sendChat = vi.fn((_messages: unknown, _context: unknown, handlers: Parameters<typeof window.api.sendChat>[2]) => {
      callbacks.push(handlers)
      return { abort: () => undefined }
    })
    vi.stubGlobal('window', { setTimeout, clearTimeout, api: { sendChat } })
    const group = createModelAbortGroup()
    const retry = runModelRetry([], () => undefined, group.createSetter(), undefined, 5, context)
    const other = runModel([], () => undefined, group.createSetter(), context)
    callbacks[0].onError?.('provider_route_unavailable')
    await Promise.resolve()
    callbacks[1].onDone?.('complete')
    group.abort()
    await vi.runAllTimersAsync()
    expect((await retry).error).toBe('已停止')
    expect((await other).ok).toBe(true)
    expect(sendChat).toHaveBeenCalledTimes(2)
  })
})

describe('six-module transient retry policy', () => {
  it('allows five extra attempts after the initial request', () => {
    expect(MODULE_TRANSIENT_RETRIES).toBe(5)
  })

  it('retries a temporary route or network failure only when there is no output', () => {
    expect(shouldRetryTransientModelResult({ ok: false, text: '', error: '模型线路连接失败，请稍后重试。' })).toBe(true)
    expect(shouldRetryTransientModelResult({ ok: false, text: '   ', error: '网络连接失败' })).toBe(true)
    expect(shouldRetryTransientModelResult({ ok: false, text: '部分内容', error: '网络连接失败' })).toBe(false)
  })

  it('does not retry user stops, authorization failures, or safety refusals', () => {
    for (const error of ['已停止', '模型服务授权失败', 'HTTP 401', '内容安全限制']) {
      expect(shouldRetryTransientModelResult({ ok: false, text: '', error })).toBe(false)
    }
    expect(shouldRetryTransientModelResult({ ok: true, text: '完整内容' })).toBe(false)
  })

  it('makes one initial request and at most five zero-output retries under the same billing task', async () => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0)
    const attempts: number[] = []
    const billingIds: string[] = []
    vi.stubGlobal('window', {
      setTimeout,
      clearTimeout,
      api: {
        sendChat: (_messages: unknown, context: { attempt: number; billingRequestId: string }, handlers: { onError: (message: string) => void }) => {
          attempts.push(context.attempt)
          billingIds.push(context.billingRequestId)
          queueMicrotask(() => handlers.onError('provider_route_unavailable'))
          return { abort: () => undefined }
        }
      }
    })
    const result = runModelRetry([], () => undefined, () => undefined, undefined, MODULE_TRANSIENT_RETRIES, {
      reportSessionId: 'test', taskType: 'module_platform_audience', taskKey: 'module-test',
      billingRequestId: 'module-test', isVision: false, sourceCount: 1, imageCount: 0
    })
    await vi.runAllTimersAsync()
    expect((await result).ok).toBe(false)
    expect(attempts).toEqual([1, 2, 3, 4, 5, 6])
    expect(new Set(billingIds)).toEqual(new Set(['module-test']))
  })
})
