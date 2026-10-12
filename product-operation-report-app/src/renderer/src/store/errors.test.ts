import { describe, expect, it } from 'vitest'
import { friendlyError } from './errors'

describe('friendlyError', () => {
  it('maps disk and network failures to novice-readable messages', () => {
    expect(friendlyError(new Error('ENOSPC: no space left'))).toMatch(/磁盘空间不足/u)
    expect(friendlyError(new Error('fetch failed ECONNRESET'))).toMatch(/网络连接失败/u)
    expect(friendlyError(new Error('Upstream response stream was interrupted'))).toMatch(/模型线路连接失败/u)
    expect(friendlyError(new Error('HTTP 503: upstream unavailable'))).toMatch(/HTTP 503/u)
    expect(friendlyError(new Error('模型流已结束，但没有返回任何内容。'))).toMatch(/没有返回内容/u)
  })

  it('preserves the known truncation cause through repeated error formatting', () => {
    const message = friendlyError('模型输出达到长度上限，本次内容不完整。请减少资料后重试。')
    expect(message).toMatch(/输出达到长度上限/u)
    expect(message).not.toMatch(/未预期|错误码/u)
    expect(friendlyError(new Error(message))).toBe(message)
  })
})
