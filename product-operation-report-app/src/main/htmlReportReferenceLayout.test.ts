import { describe, expect, it } from 'vitest'
import { buildHtmlReportPresentation, markdownToHtmlDocument, parseHtmlReportModel } from './htmlReport'
import { renderReferenceGenderOverview, renderAudienceTraitTags, renderReferenceFactValue, renderReferenceMaterialCounts } from './htmlReportReferenceLayout'

const fixture = `# 示例产品报告
## M1 产品信息
1. 产品基础
信息：示例酸菜。
来源：示例手卡
## M2 成交人群分析
${['视频号', '抖店罗盘', '巨量云图'].map((name, index) => `### 平台：${name}\n### 1. 性别\n信息：女性${68 + index * 3}%，男性${32 - index * 3}%\n来源：示例画像`).join('\n')}
### 多平台核心人群TOP5
| 优先级 | 人群标签 | 占比/特征 | 决策动机 | 内容语言 |
|---|---|---|---|---|
| 第一主力 | 家庭用户 | 三个平台均有来源 | 关注便利 | 展示操作步骤 |
## M3 内容素材判断
暂无分析
## M4 卖点提炼与排序
暂无分析
## M5 用户真实需求VOC
暂无分析
## M6 人群×卖点×场景匹配
暂无分析`

describe('reference report data integrity', () => {
  it('summarizes audience tags without transferring metrics between sources', () => {
    const value = '巨量千川/抖音女性71.43%、36-40岁26.27%、精致妈妈20.32%；未标注画像女性78.14%、已育72.96%'
    const tags = renderAudienceTraitTags(value, true)
    expect(tags.match(/class="audience-trait-tag"/gu)).toHaveLength(3)
    expect(tags).toContain('千川/抖音女性71.43%')
    expect(tags).toContain('千川/抖音36-40岁26.27%')
    expect(tags).toContain('未标注画像女性78.14%')
    expect(tags).not.toContain('千川/抖音女性78.14%')
    expect(tags).toContain('完整画像见下方明细')
  })
  it('parses separately enumerated city percentages without merging their labels', () => {
    const model = parseHtmlReportModel('# 报告\n## M2 成交人群分析\n平台：抖店罗盘\n地域\n信息：杭州市5.70%、宁波市1.63%\n来源：成交画像')
    const rows = model.sections[0].tables.flatMap(table => table.rows)
    expect(rows.some(row => row.includes('杭州市') && row.includes('5.70%'))).toBe(true)
    expect(rows.some(row => row.includes('宁波市') && row.includes('1.63%'))).toBe(true)
  })

  it('preserves actual matching reasons and only displays strategies supplied by the report', async () => {
    const markdown = '# 报告\n## M6 人群×卖点×场景匹配\nTOP1\n核心人群：家庭用户\n核心卖点：省时\n真实场景：晚餐准备\n匹配理由：家庭晚餐准备时间有限。\n场景依据：需求场景｜SC-1234abcd-0001'
    const html = await markdownToHtmlDocument(markdown)
    expect(html).toContain('<span>匹配理由</span><strong>家庭晚餐准备时间有限。</strong>')
    expect(html).not.toContain('<span>内容策略 · 待测试</span>')
    expect(html).toContain('SC-1234abcd-0001')
    const withStrategy = await markdownToHtmlDocument(markdown + '\n内容策略：演示晚餐准备步骤。')
    expect(withStrategy).toContain('<span>内容策略 · 待测试</span><strong>演示晚餐准备步骤。</strong>')
  })

  it('keeps video totals separate from script-unit counts', () => {
    const model = parseHtmlReportModel('# 报告\n## M3 内容素材判断\n自有素材：10条\n竞品素材：10条原视频/有效数据行；F框架簇按12个脚本单元统计。')
    const html = renderReferenceMaterialCounts(model.sections[0])
    expect(html.match(/<strong>10<\/strong>/gu)).toHaveLength(2)
    expect(html).toContain('12个脚本单元')
    expect(renderReferenceMaterialCounts({ ...model.sections[0], markdown: '数量未知' })).toContain('待确认')
  })

  it('retains audience and does not absorb ranking rows into the last need group', () => {
    const model = parseHtmlReportModel('# 报告\n## M3 内容素材判断\n### 自有素材TOP1｜开头\n框架类型：场景型\n数据依据：2条\n主要人群：家庭用户\n可复用方向：演示做饭\n## M4 卖点提炼与排序\n### 4. 情感需求\nTOP1\n卖点：省时\n买点：少做准备\n### 二、核心卖点总排序\n### TOP1｜省时\n需求类型：情感\n买点：少做准备')
    expect(model.sections[0].tables[0].rows[0][3]).toBe('家庭用户')
    expect(model.sections[1].tables[0].rows).toHaveLength(1)
  })

  it('separates source groups without assigning unlabelled metrics to a platform', () => {
    const tags = renderAudienceTraitTags('视频号大于60岁44.57%、0-100元80.08%；未标注画像都市银发19.03%；主力商品客单价20.68元')
    expect(tags.match(/class="audience-trait-group"/gu)).toHaveLength(3)
    expect(tags).toContain('<span>0-100元</span><b>80.08%</b>')
    expect(tags).toContain('未标注画像</span>')
    expect(tags).toContain('补充依据</span>')
    expect(tags).toContain('<span>主力商品客单价</span><b>20.68元</b>')
  })

  it('keeps qualifications intact while emphasizing numeric product facts', () => {
    const value = '整颗300g3袋25.9元；未见第三方检测报告。'
    const html = renderReferenceFactValue('价格', value)
    expect(html.replace(/<[^>]+>/gu, '')).toBe(value)
    expect(html).toContain('<strong>25.9元</strong>')
    expect(html).toContain('未见第三方检测报告。')
  })
  it('only plots complete gender distributions, preserving each platform independently', () => {
    const markdown = fixture.replace('男性32%', '男性20%')
    const plan = buildHtmlReportPresentation(parseHtmlReportModel(markdown)).sections.find(section => section.sectionNumber === 'M2')!
    const overview = renderReferenceGenderOverview(plan)
    expect(overview).not.toContain('视频号')
    expect(overview).toContain('抖店罗盘 女性71%，男性29%')
    expect(overview).toContain('巨量云图 女性74%，男性26%')
  })

  it('keeps full evidence accessible when the audience table becomes strategy cards', async () => {
    const html = await markdownToHtmlDocument(fixture)
    const details = html.match(/<details class="evidence-disclosure module-details profile-details">([\s\S]*?)<\/details>/u)?.[1] || ''
    expect(details).toContain('多平台核心人群TOP5')
    expect(details).toContain('三个平台均有来源')
    expect(html).toContain('reference-audience-strategies')
    expect(html.match(/class="reference-summary-card"/gu)).toHaveLength(6)
    expect(html).toContain('本模块阅读与行动建议')
  })
})
