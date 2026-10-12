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
})
