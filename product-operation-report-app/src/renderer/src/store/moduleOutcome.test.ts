import { describe, expect, it } from 'vitest'
import { completeModuleAsInsufficient } from './moduleOutcome'

describe('canonical module outcome adapter', () => {
  it('records one insufficient outcome across journal, task record and module state', () => {
    const result = completeModuleAsInsufficient(
      {},
      {},
      'session:module:v2:voc',
      'voc',
      '未上传用户声音与反馈。',
      '2026-08-30T08:10:00.000Z',
      'input:voc'
    )

    expect(result.output).toBe('暂无分析：未上传用户声音与反馈。')
    expect(result.taskJournal['session:module:v2:voc']).toEqual({
      kind: 'module',
      status: 'complete',
      output: '暂无分析：未上传用户声音与反馈。',
      inputFingerprint: 'input:voc',
      updatedAt: '2026-08-30T08:10:00.000Z'
    })
    expect(result.taskRecords['session:module:v2:voc']).toMatchObject({
      kind: 'MODULE_ANALYSIS',
      executionStatus: 'SUCCEEDED',
      resultStatus: 'INSUFFICIENT',
      moduleKey: 'voc',
      inputFingerprint: 'input:voc',
      updatedAt: '2026-08-30T08:10:00.000Z',
      migratedFromLegacy: false
    })
    expect(result.moduleState).toEqual({
      status: 'skipped',
      message: '暂无分析：未上传用户声音与反馈。',
      updatedAt: '2026-08-30T08:10:00.000Z'
    })
  })

  it('does not double-prefix an existing no-analysis result', () => {
    const result = completeModuleAsInsufficient(
      {},
      {},
      'session:module:v2:product-info',
      'product-info',
      '暂无分析：未上传产品与供给资料。',
      '2026-08-30T08:11:00.000Z'
    )
    expect(result.output).toBe('暂无分析：未上传产品与供给资料。')
  })
})
