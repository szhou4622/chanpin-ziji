import { describe, expect, it } from 'vitest'
import { shouldRetryModelRun } from './analysis'
import { friendlyError } from './errors'

describe('reconcile-safe model retry classification', () => {
  it('retries a managed-proxy 409 only through the next admission/reconcile cycle', () => {
    const message = friendlyError('HTTP 409：same batch still processing')
    expect(message).toContain('上一条模型任务')
    expect(shouldRetryModelRun(message)).toBe(true)
  })

  it('does not retry user stop or authorization failures', () => {
    expect(shouldRetryModelRun('已停止。')).toBe(false)
    expect(shouldRetryModelRun('模型服务授权失败，请联系软件管理员。')).toBe(false)
  })

  it('keeps ordinary semantic failures non-retryable', () => {
    expect(shouldRetryModelRun('结构检查未通过：缺少证据字段')).toBe(false)
  })
})
