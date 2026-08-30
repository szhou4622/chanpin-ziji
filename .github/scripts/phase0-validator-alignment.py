from pathlib import Path

modules = Path('product-operation-report-app/src/renderer/src/modules.ts')
text = modules.read_text(encoding='utf-8')
replacements = {
    "if (ranks.length !== 10 || ranks.some((rank, rankIndex) => rank !== rankIndex + 1)) {\n      errors.push(`${group.heading}必须完整包含TOP1-TOP10`)\n    }":
    "if (ranks.length < 1 || ranks.length > 10 || ranks.some((rank, rankIndex) => rank !== rankIndex + 1)) {\n      errors.push(`${group.heading}必须包含连续的TOP1-TOPN，且N不得超过10`)\n    }",
    "if (!ordered(value, ['TOP1', 'TOP2', 'TOP3', 'TOP4', 'TOP5'])) errors.push('人群卖点场景模块缺少TOP1-TOP5')":
    "const sceneRanks = [...value.matchAll(/^#{0,6}\\s*TOP\\s*(\\d{1,2})(?:\\s*[｜|].*)?$/gimu)].map((match) => Number(match[1]))\n    if (sceneRanks.length < 1 || sceneRanks.length > 5 || sceneRanks.some((rank, index) => rank !== index + 1)) {\n      errors.push('人群卖点场景模块必须包含连续的TOP1-TOPN，且N不得超过5')\n    }",
    "每组必须有TOP1到TOP10共10条，不能只输出第一组。":
    "四组都必须输出；每组根据现有证据输出TOP1到TOPN，N为1-10。不能只输出第一组；不足10条时必须少输出，禁止为了凑满TOP10编造内容。"
}
for old, new in replacements.items():
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'modules.ts expected one match, found {count}: {old[:80]!r}')
    text = text.replace(old, new)
modules.write_text(text, encoding='utf-8')

tests = Path('product-operation-report-app/src/renderer/src/modules.test.ts')
text = tests.read_text(encoding='utf-8')
start = text.index("  it('requires all four VOC groups and keeps TOP labels separate from user terms', () => {")
end = text.index("\n\n  it('assembles M1-M6 in order", start)
replacement = r'''  it('requires all four VOC groups but allows evidence-supported sparse TOP results', () => {
    const groups = [
      { heading: '1. 隐形需求 TOP10', field: '需求', positive: false },
      { heading: '2. 购买顾虑 TOP10', field: '顾虑', positive: false },
      { heading: '3. 高频问题 TOP10', field: '问题', positive: false },
      { heading: '4. 正向反馈 TOP10', field: '反馈', positive: true }
    ]
    const buildVoc = (count: number): string => groups.map((group) => [
      group.heading,
      ...Array.from({ length: count }, (_, index) => [
        `TOP${index + 1}`,
        `${group.field}：真实词${index + 1}`,
        ...(group.positive ? ['认可类型：产品体验', '认可价值：使用更方便'] : []),
        `频次：${20 - index}次`,
        `占比：${10 - index / 2}%`,
        '来源分布：自营',
        `代表原话：用户原话${index + 1}`,
        `来源：评价表｜${index + 1}`
      ].join('\n'))
    ].join('\n')).join('\n\n')

    const full = buildVoc(10)
    const sparse = buildVoc(4)
    expect(validateModuleOutput('voc', full, 'v2')).toEqual([])
    expect(validateModuleOutput('voc', sparse, 'v2')).toEqual([])
    expect(validateModuleOutput('voc', sparse.replace('频次：20次\n占比：10%', '频次：无精确频次｜占比无法计算'), 'v2')).toEqual([])
    expect(validateModuleOutput('voc', buildVoc(11), 'v2')).toContain(
      '1. 隐形需求 TOP10必须包含连续的TOP1-TOPN，且N不得超过10'
    )
    expect(validateModuleOutput('voc', sparse.split('2. 购买顾虑 TOP10')[0], 'v2')).toContain(
      'VOC必须按顺序完整包含隐形需求、购买顾虑、高频问题、正向反馈四组TOP10'
    )
    const module = REPORT_MODULES_V2.find((item) => item.key === 'voc')!
    const retry = moduleValidationRetryInstruction(module, ['缺少三组'], 1)
    expect(retry).toContain('不能只输出第一组')
    expect(retry).toContain('不足10条时必须少输出')
    expect(retry).not.toContain('每组必须有TOP1到TOP10共10条')
  })'''
text = text[:start] + replacement + text[end:]

marker = "  it('treats evidence-bound no-result output as 暂无分析 instead of a module failure', () => {"
insert_at = text.index(marker)
scene_test = r'''  it('allows one to five evidence-supported audience-selling-point-scene combinations', () => {
    const buildScene = (count: number): string => [
      '核心人群 × 卖点 × 场景 TOP5',
      ...Array.from({ length: count }, (_, index) => [
        `TOP${index + 1}`,
        `核心人群：人群${index + 1}`,
        '人群依据：成交画像',
        `核心卖点：卖点${index + 1}`,
        '卖点依据：产品事实',
        `真实场景：场景${index + 1}`,
        '场景依据：用户反馈'
      ].join('\n'))
    ].join('\n\n')

    expect(validateModuleOutput('audience-sp-scene', buildScene(3), 'v2')).toEqual([])
    expect(validateModuleOutput('audience-sp-scene', buildScene(5), 'v2')).toEqual([])
    expect(validateModuleOutput('audience-sp-scene', buildScene(6), 'v2')).toContain(
      '人群卖点场景模块必须包含连续的TOP1-TOPN，且N不得超过5'
    )
  })

'''
text = text[:insert_at] + scene_test + text[insert_at:]
tests.write_text(text, encoding='utf-8')
