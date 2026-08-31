import { describe, expect, it } from 'vitest'
import {
  ProxyRequestTracker,
  assertSafeProxyRequestId,
  assertSafeProxyTaskKey,
  parseProxyRequestState,
  parseProxyRequestStates
} from './proxyRequestLifecycle'

const ROOT = 'b4f81b86-1a5b-4e39-830e-1271165bb8ee'
const FALLBACK = `${ROOT}:fallback:1`

describe('proxy request lifecycle boundary', () => {
  it('accepts only server-compatible request and task identifiers', () => {
    expect(assertSafeProxyRequestId(ROOT)).toBe(ROOT)
    expect(assertSafeProxyRequestId(FALLBACK)).toBe(FALLBACK)
    expect(assertSafeProxyTaskKey('report-a:module:v2:product-info')).toBe('report-a:module:v2:product-info')
    expect(() => assertSafeProxyTaskKey('bad%2Ftask')).toThrow('模型任务标识无效')
    expect(() => assertSafeProxyTaskKey('../wallet')).toThrow('模型任务标识无效')
    expect(() => assertSafeProxyRequestId(`${ROOT}:fallback:9`)).toThrow('模型请求标识无效')
  })

  it('parses only bounded request lifecycle metadata', () => {
    const parsed = parseProxyRequestState({
      requestId: ROOT,
      reportSessionId: 'report-a',
      taskKey: 'report-a:module:v2:product-info',
      taskType: 'module_product_info',
      model: 'gpt-5.5',
      attempt: 1,
      status: 'running',
      cancelRequested: true,
      upstreamSubmitted: true,
      usageSource: 'missing',
      startedAt: '2026-09-01T00:00:00Z',
      endedAt: null,
      ignoredContent: 'must not leak into the typed result'
    })
    expect(parsed).toEqual({
      requestId: ROOT,
      reportSessionId: 'report-a',
      taskKey: 'report-a:module:v2:product-info',
      taskType: 'module_product_info',
      model: 'gpt-5.5',
      attempt: 1,
      status: 'running',
      cancelRequested: true,
      upstreamSubmitted: true,
      usageSource: 'missing',
      startedAt: '2026-09-01T00:00:00Z'
    })
    expect(parseProxyRequestStates([parsed])).toEqual([parsed])
  })

  it('tracks the current concrete fallback request without crossing renderer owners', () => {
    const tracker = new ProxyRequestTracker()
    tracker.claim(ROOT, 10, 'report-a:module:v2:product-info')
    expect(tracker.setCurrent(ROOT, 11, FALLBACK)).toBe(false)
    expect(tracker.setCurrent(ROOT, 10, FALLBACK)).toBe(true)
    expect(tracker.get(ROOT, 10)).toEqual({
      rootRequestId: ROOT,
      ownerId: 10,
      taskKey: 'report-a:module:v2:product-info',
      currentRequestId: FALLBACK
    })
    expect(tracker.get(ROOT, 11)).toBeUndefined()
  })

  it('drains one renderer independently and makes repeated cleanup idempotent', () => {
    const tracker = new ProxyRequestTracker()
    const other = 'c4f81b86-1a5b-4e39-830e-1271165bb8ee'
    tracker.claim(ROOT, 10, 'task:a')
    tracker.claim(other, 11, 'task:b')
    expect(tracker.drainOwner(10)).toEqual([{ rootRequestId: ROOT, ownerId: 10, taskKey: 'task:a' }])
    expect(tracker.drainOwner(10)).toEqual([])
    expect(tracker.size).toBe(1)
    expect(tracker.drainAll()).toEqual([{ rootRequestId: other, ownerId: 11, taskKey: 'task:b' }])
    expect(tracker.size).toBe(0)
  })
})
