import { describe, expect, it } from 'vitest'
import { markdownToHtmlDocument, parseHtmlReportModel } from './htmlReport'
import { resolveHtmlReportDesign } from './htmlReportDesign'

function report(product: string, brand = '示例品牌', additional = ''): string {
  return `# 产品内容策略报告\n\n## M1 产品信息\n\n1. 产品基础\n信息：${product}；品牌${brand}。\n来源：产品手卡\n\n${additional}`
}

describe('merchant report design', () => {
  it.each([
    ['发酵酸菜/酱腌菜', 'household-field-guide'],
    ['补水面霜', 'restrained-catalogue'],
    ['记忆棉枕头', 'material-editorial'],
    ['无线耳机', 'technical-workbench'],
    ['维生素膳食补充剂', 'calm-evidence'],
    ['工业机床', 'utilitarian-decision-brief'],
    ['儿童积木玩具', 'energetic-social']
  ])('uses own product identity to style %s', (product, expected) => {
    const design = resolveHtmlReportDesign(parseHtmlReportModel(report(product)))
    expect(design.direction).toBe(expected)
    expect(design.reason).toBe('product-category')
    expect(design.productName).toBe(product)
    expect(design.brandName).toBe('示例品牌')
  })

  it('keeps the same merchant signature across its products and repeated exports', () => {
    const food = resolveHtmlReportDesign(parseHtmlReportModel(report('发酵酸菜', '盐中甜')))
    const otherFood = resolveHtmlReportDesign(parseHtmlReportModel(report('酸菜调味品', '盐中甜')))
    expect(food.variant).toBe(otherFood.variant)
    expect(food.tokens).toEqual(otherFood.tokens)
    expect(food).toEqual(resolveHtmlReportDesign(parseHtmlReportModel(report('发酵酸菜', '盐中甜'))))
  })

  it('does not infer a merchant category from competitors, ingredients, comments or audience preferences', () => {
    const markdown = '# 产品内容策略报告\n\n## M1 产品信息\n5. 原料/成分/材质\n信息：蛋白粉、酸菜、面霜\n来源：待核\n\n## M2 成交人群分析\n购买偏好：面霜、食品\n\n## M3 内容素材判断\n竞品：无线耳机\n\n## M5 用户真实需求VOC\n评论：家里枕头不错'
    const design = resolveHtmlReportDesign(parseHtmlReportModel(markdown))
    expect(design.direction).toBe('neutral-evidence')
    expect(design.reason).toBe('fallback')
    expect(design.productName).toBe('')
  })

  it('falls back for ambiguous categories and preserves a complete explicit visual brief', () => {
    expect(resolveHtmlReportDesign(parseHtmlReportModel(report('面霜和零食组合'))).reason).toBe('fallback')
    const brief = '<!-- Product visual brief\nrole: 节日礼赠\naudience: 送礼用户\nscene: 节日\nvalue-signal: gifting\ntrust-model: craft\ndesign-direction: restrained-catalogue\nevidence-confidence: confirmed\n-->'
    const design = resolveHtmlReportDesign(parseHtmlReportModel(`${brief}\n${report('酸菜礼盒')}`))
    expect(design.direction).toBe('restrained-catalogue')
    expect(design.reason).toBe('visual-brief')
  })

  it('varies typography and cover structures without changing evidence content or offline restrictions', async () => {
    const food = await markdownToHtmlDocument(report('发酵酸菜', '盐中甜'))
    const beauty = await markdownToHtmlDocument(report('补水面霜', '示例美妆'))
    expect(food).toContain('data-report-style="household-field-guide"')
    expect(beauty).toContain('data-report-style="restrained-catalogue"')
    expect(food).toContain('信息：发酵酸菜；品牌盐中甜。')
    expect(food).toContain("script-src 'none'")
    expect(food).toContain("connect-src 'none'")
    expect(food).not.toMatch(/<script\b|<link\s[^>]*href="https?:/iu)
    expect(resolveHtmlReportDesign(parseHtmlReportModel(report('发酵酸菜'))).tokens.fontDisplay)
      .not.toBe(resolveHtmlReportDesign(parseHtmlReportModel(report('补水面霜'))).tokens.fontDisplay)
  })
})
