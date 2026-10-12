import { afterEach, describe, expect, it, vi } from 'vitest'
import { MODULE_TRANSIENT_RETRIES, runModelRetry, shouldRetryTransientModelResult } from './analysis'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
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
