import { describe, expect, it } from 'vitest'
import { validateReportEvidenceLinks, validateReportStructure } from './validate'

describe('report evidence identity compatibility', () => {
  it('accepts both legacy and SHA-backed evidence ids from the cleaning ledger', () => {
    const legacy = 'POR-R-32F24FA0-000001'
    const current = 'POR-T-ABABABABABABABABABABABAB-1234567890AB-000001'
    const audit = validateReportEvidenceLinks(`金额 100，来源 ${legacy}；转化 20，来源 ${current}`, `${legacy}\n${current}`)
    expect(audit.errors).toEqual([])
    expect(audit.linkedIds).toBe(2)
  })
})

describe('six-module report structure', () => {
  it('accepts a continuous M1-M6 report and an optional legacy appendix', () => {
    const report = [
      '# 产品与内容经营报告',
      ...Array.from({ length: 6 }, (_, index) => `## M${index + 1} 模块${index + 1}\n内容${index + 1}`),
      '## A1 旧版对标附录（不参与六模块分析）',
      '旧版内容',
      '> 本报告内容由 AI 生成，请谨慎参考。'
    ].join('\n\n')
    expect(validateReportStructure(report)).toEqual([])
  })

  it('still rejects a missing six-module chapter', () => {
    const report = [
      '# 产品与内容经营报告',
      ...[1, 2, 3, 4, 6].map((id) => `## M${id} 模块${id}\n内容${id}`),
      '> 本报告内容由 AI 生成，请谨慎参考。'
    ].join('\n\n')
    expect(validateReportStructure(report)).toContain('报告缺少标准章节：## M5。')
  })
})
