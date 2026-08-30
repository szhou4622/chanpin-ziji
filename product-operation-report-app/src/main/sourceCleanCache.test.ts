import { describe, expect, it } from 'vitest'
import { sourceCleanCacheKey } from './sourceCleanCache'

describe('source clean cache identity', () => {
  it('includes the full source note instead of only the first 4000 characters', () => {
    const sharedPrefix = '说明'.repeat(2_000)
    const base = {
      name: '用户评价.csv',
      kind: 'table' as const,
      text: '评价内容,评分\n很好用,5',
      attribution: '自有数据',
      kindV1: 'voice-data' as const
    }
    const first = sourceCleanCacheKey({ ...base, note: `${sharedPrefix}A` }, 'gpt-test')
    const second = sourceCleanCacheKey({ ...base, note: `${sharedPrefix}B` }, 'gpt-test')

    expect(first).not.toBe(second)
  })
})
