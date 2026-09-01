import { describe, expect, it } from 'vitest'
import { ProxyRequestTracker } from './proxyRequestLifecycle'

describe('proxy logical-task admission', () => {
  it('finds an already tracked logical task across renderer owners', () => {
    const tracker = new ProxyRequestTracker()
    const first = '11111111-1111-4111-8111-111111111111'
    const second = '22222222-2222-4222-8222-222222222222'
    const taskKey = 'report-a:module:v2:product-info'
    tracker.claim(first, 10, taskKey)

    expect(tracker.findByTaskKey(taskKey)?.rootRequestId).toBe(first)
    expect(tracker.findByTaskKey(taskKey, first)).toBeUndefined()
    expect(() => tracker.claim(second, 20, taskKey)).toThrow(/同一模型任务正在处理中/u)

    tracker.claim(second, 20, 'report-a:module:v2:voc')
    expect(tracker.findByTaskKey('report-a:module:v2:voc')?.ownerId).toBe(20)
  })
})
