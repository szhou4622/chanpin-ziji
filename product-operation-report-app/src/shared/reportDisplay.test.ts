import { describe, expect, it } from 'vitest'
import { buildEvidenceSourceNameMap, reportMarkdownForDisplay, splitReportAtSellingPoints } from './reportDisplay'

describe('reportMarkdownForDisplay', () => {
  it('hides internal evidence IDs without discarding provenance wording', () => {
    const source = [
      '核心成交规模：211985.04元；来源：`POR-R-32F24FA0-000001`、`POR-R-32F24FA0-000036`。',
      '| 场景 | 酸菜炒肉。来源： POR-T-554F9487-000001、POR-R-F6769716-000047 |'
    ].join('\n')
    const visible = reportMarkdownForDisplay(source)
    expect(visible).not.toMatch(/POR-[RTI]-/u)
    expect(visible).toContain('来源：已核验资料')
    expect(visible).toContain('211985.04元')
    expect(visible).toContain('酸菜炒肉')
  })

  it('also hides internal batch receipts if they leak into a report', () => {
    expect(reportMarkdownForDisplay('依据 POR-B-ABCDEF12-0001|ROWS:1-50|COUNT:50'))
      .toBe('依据 已核验资料')
  })

  it('shows the uploaded file name when the cleaning ledger can resolve the ID', () => {
    const map = buildEvidenceSourceNameMap([{
      name: '经营数据表.xlsx',
      text: '__证据ID,成交金额\nPOR-R-32F24FA0-000001,211985.04'
    }])
    expect(reportMarkdownForDisplay('来源：POR-R-32F24FA0-000001', map))
      .toBe('来源：经营数据表.xlsx')
  })

  it('replaces internal M1-M6 headings with user-facing decision names', () => {
    const internal = [
      '# 产品内容策略报告',
      '## M1 产品信息',
      '## M2 成交人群分析',
      '## M3 内容素材判断',
      '## M4 卖点提炼与排序',
      '## M5 用户真实需求VOC',
      '## M6 人群×卖点×场景匹配'
    ].join('\n')
    const visible = reportMarkdownForDisplay(internal)
    expect(visible).toContain('## 内容洞察决策一：产品信息')
    expect(visible).toContain('## 内容洞察决策二：成交人群分析')
    expect(visible).toContain('## 内容洞察决策三：内容素材判断')
    expect(visible).toContain('## 内容洞察决策四：卖点提炼与排序')
    expect(visible).toContain('## 内容洞察决策五：用户真实需求VOC')
    expect(visible).toContain('## 内容洞察决策六：人群×卖点×场景匹配')
    expect(visible).not.toMatch(/^##\s+M[1-6]\s+/mu)
  })

  it('does not partially rename a legacy or incomplete module report', () => {
    expect(reportMarkdownForDisplay('## M1 产品信息\n\n## M2 平台人群数据'))
      .toBe('## M1 产品信息\n\n## M2 平台人群数据')
  })
})

describe('splitReportAtSellingPoints', () => {
  it('places the material cloud after M4, never ahead of M1', () => {
    const markdown = '# 报告\n\n## 内容洞察决策一：产品信息\n产品信息\n\n## 内容洞察决策四：卖点提炼与排序\n\n卖点内容'
    const sections = splitReportAtSellingPoints(markdown)
    expect(sections).not.toBeNull()
    expect(sections?.[0]).toContain('## 内容洞察决策一：产品信息')
    expect(sections?.[0]).toMatch(/## 内容洞察决策四：卖点提炼与排序$/u)
    expect(sections?.[1]).toContain('卖点内容')
  })

  it('also supports the internal M4 heading and does not insert into reports without M4', () => {
    expect(splitReportAtSellingPoints('## M4 卖点提炼与排序\n正文')).toEqual([
      '## M4 卖点提炼与排序', '\n正文'
    ])
    expect(splitReportAtSellingPoints('## M1 产品信息\n正文')).toBeNull()
  })
})
