import { plainText, shorten, type HtmlReportModel, type HtmlReportSection } from './htmlReportModel'
import type { HtmlReportPresentation, HtmlReportSectionPresentation } from './htmlReportPresentation'

const escape = (value: string): string => value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

const MODULES = [
  { label: '产品信息', title: '产品信息：先确认能讲什么，再交给内容团队', use: '新品建档、编写脚本和制作商品画面前，先统一产品信息与素材边界。', actions: ['核对包装、规格、配料、工艺与现行价格。', '把已确认的产品特点转成用户能看懂的使用场景。', '将缺失或冲突的信息单独列出，补充证据后再使用。'], deliverable: '产品事实与证据表：事实、证据、适用规格、是否可用。', next: '产品信息 → 卖点提炼 → 内容表达。' },
  { label: '主攻人群', title: '成交人群：确定先给谁看，指导角色与场景', use: '选择内容主角、表达方式和使用场景时，结合各平台的成交画像判断。', actions: ['分平台阅读画像，保留各自统计口径。', '把年龄、消费特征与实际需求联系起来。', '将人群判断作为待测试方向，观察后续内容表现。'], deliverable: '核心人群卡：人群特征、数据依据、购买动机与表达方向。', next: '成交画像 → 核心人群 → 场景匹配。' },
  { label: '内容方向', title: '内容素材：比较自有和竞品，找下一批该补什么', use: '回顾已有内容、安排下一批选题和拍摄计划时，辨别已覆盖与待补充的方向。', actions: ['分别梳理自有素材和竞品素材的讲述结构。', '记录可以复用的开头、展示方式与证明内容。', '结合自己的产品事实，安排下一批内容测试。'], deliverable: '素材补充清单：选题、开头、展示方式、证据与适用人群。', next: '素材对照 → 补充机会 → 拍摄计划。' },
  { label: '核心卖点', title: '卖点：把产品特点翻译成购买理由，再设计证明', use: '整理产品手卡、确定脚本重点、设计展示画面时，从用户能感知的好处出发。', actions: ['区分产品特点、用户利益和证明依据。', '结合人群与场景，确定优先测试的卖点。', '为每个卖点安排可拍摄、可核实的证明画面。'], deliverable: '卖点与证明清单：产品特点、用户利益、证据与展示方法。', next: '产品特点 → 用户利益 → 证明画面。' },
  { label: '用户声音', title: '用户 VOC：把真实问题变成开头、答疑和产品反馈', use: '设计视频开头、完善商品答疑和复盘用户反馈时，回到用户的真实表达。', actions: ['按需求、顾虑、疑问与反馈分类阅读原话。', '为反复出现的问题安排解释和展示内容。', '保留来源与样本范围，避免将个别意见泛化。'], deliverable: '用户问题与回应表：原话、来源、需求解读和回应方向。', next: '用户原话 → 需求解读 → 答疑与内容。' },
  { label: '核心场景', title: '人群×卖点×场景：组合成可执行的内容决策', use: '安排选题、拍摄和脚本制作时，把人群、卖点与真实场景放在同一条路径中。', actions: ['为每条内容确定一个主要人群和使用场景。', '选择一个有依据的重点卖点，匹配展示方式。', '制作样片并记录结果，持续调整内容组合。'], deliverable: '内容计划卡：人群、场景、重点卖点、内容表达与依据。', next: '人群与场景 → 卖点与证明 → 内容测试。' }
]

export function referenceSectionSummary(section: HtmlReportSection): { headline: string; detail: string } {
  const clean = (value: string): string => plainText(value).replace(/^TOP\s*\d+\s*[｜|]?\s*/iu, '').trim()
  const find = (pattern: RegExp) => section.tables.find(table => table.headers.some(header => pattern.test(header)))
  const cell = (table: HtmlReportSection['tables'][number] | undefined, pattern: RegExp, row = 0): string => {
    const index = table?.headers.findIndex(header => pattern.test(header)) ?? -1
    return index >= 0 ? clean(table?.rows[row]?.[index] || '') : ''
  }
  if (section.number === 'M1') {
    const table = section.tables.find(table => table.context === '产品九维事实') || section.tables[0]
    const facts = table?.rows.filter(row => /原料|工艺|产品属性/u.test(row[0])) || []
    return { headline: '先核实产品事实', detail: facts.slice(0, 2).map(row => clean(row[1]).split(/[；;。]/u)[0]).join('；') || clean(table?.rows[0]?.[1] || '') }
  }
  if (section.number === 'M2') {
    const table = find(/人群标签/u)
    return { headline: cell(table, /人群标签/u).split(/[｜|]/u)[0] || '分平台确认成交人群', detail: cell(table, /决策动机/u) || '分别阅读各平台画像，再确定内容主角与表达方式。' }
  }
  if (section.number === 'M3') {
    const table = section.tables.find(table => table.context === '补充机会') || section.tables[0]
    const parts = clean(table?.rows[0]?.[0] || '').split(/[｜|]/u)
    return { headline: parts.slice(1, 3).join(' · ') || parts[0] || '自有素材与竞品对照', detail: clean(table?.rows[0]?.[2] || '').split(/。/u)[0] }
  }
  if (section.number === 'M4') {
    const table = find(/真实卖点|用户视角卖点/u)
    return { headline: cell(table, /真实卖点|用户视角卖点/u) || '产品特点与用户收益', detail: table ? `优先表达：${table.rows.slice(0, 3).map((_, i) => cell(table, /真实卖点|用户视角卖点/u, i)).filter(Boolean).join('、')}` : '按品质、价格、健康与情感需求整理已有卖点。' }
  }
  if (section.number === 'M5') {
    const tables = section.tables.filter(table => table.headers.some(header => /需求词/u.test(header)))
    return { headline: tables.slice(0, 2).map(table => cell(table, /需求词/u)).filter(Boolean).join(' · ') || '用户需求与顾虑', detail: tables.slice(0, 2).map(table => cell(table, /代表原话/u)).filter(Boolean).map(quote => `“${quote}”`).join('；') }
  }
  if (section.number === 'M6') {
    const table = find(/核心场景/u)
    return { headline: cell(table, /核心场景/u) || '人群、卖点与场景匹配', detail: cell(table, /匹配理由/u) || [cell(table, /成交人群/u), cell(table, /核心卖点/u)].filter(Boolean).join(' · ') }
  }
  return { headline: section.title, detail: section.paragraphs[0] || section.listItems[0] || '本模块资料待补充。' }
}

function excerpt(section: HtmlReportSection): string {
  return shorten(referenceSectionSummary(section).detail || '本模块资料待补充，查看正文确认已有信息。', 130)
}

export function renderAudienceTraitTags(value: string, compact = false): string {
  // Keep source boundaries explicit. Unlabelled groups never inherit a platform.
  const groups = plainText(value).split(/[；;]+/u).map(part => part.trim()).filter(Boolean)
  if (compact) {
    const parsed = groups.map(group => {
      const source = group.match(/^(巨量千川\s*[/／]\s*抖音|巨量千川|巨量云图|抖店罗盘|视频号|未标注画像|抖店|抖音|快手|小红书)/u)?.[0] || '补充依据'
      const content = source === '补充依据' ? group : group.slice(source.length).replace(/^[：:\s]+/u, '')
      return { source, tags: content.split(/[，、]|(?<=[%元]),/u).map(text => text.trim()).filter(Boolean) }
    })
    // Select a small evidence summary, retaining the full original traits in the module disclosure.
    const selected = parsed.flatMap((group, groupIndex) => group.tags.slice(0, 1).map(text => ({ ...group, groupIndex, text }))).slice(0, 3)
    for (let groupIndex = 0; groupIndex < parsed.length && selected.length < 3; groupIndex++) {
      for (const text of parsed[groupIndex].tags.slice(1)) {
        if (selected.length === 3) break
        selected.push({ ...parsed[groupIndex], groupIndex, text })
      }
    }
    selected.sort((a, b) => a.groupIndex - b.groupIndex)
    return `<div class="reference-audience-traits reference-audience-traits--compact">${selected.map(({ source, text }, index) => `<span class="audience-trait-tag" data-trait-color="${index}" title="${escape(source + '：' + text)}">${escape((source === '补充依据' ? '' : source.replace('巨量千川', '千川')) + text)}</span>`).join('')}</div><small class="reference-audience-sources">来源：${escape([...new Set(parsed.map(group => group.source))].join('、'))}；完整画像见下方明细。</small>`
  }
  return `<div class="reference-audience-traits">${groups.map(group => {
    const source = group.match(/^(巨量千川\s*[/／]\s*抖音|巨量千川|巨量云图|抖店罗盘|视频号|未标注画像|抖店|抖音|快手|小红书)/u)?.[0] || ''
    const content = group.slice(source.length).replace(/^[：:\s]+/u, '')
    const tags = content.split(/[，、]|(?<=[%元]),/u).map(part => part.trim()).filter(Boolean)
    return `<section class="audience-trait-group"><span class="audience-trait-source">${escape(source || '补充依据')}</span><div class="audience-trait-tags">${tags.map(tag => {
      const metric = tag.match(/^(.*?)([≥≤<>]?\s*\d+(?:\.\d+)?(?:%|元))[。.]?$/u)
      return metric ? `<span class="audience-trait-tag"><span>${escape(metric[1])}</span><b>${escape(metric[2])}</b></span>` : `<span class="audience-trait-note">${escape(tag)}</span>`
    }).join('')}</div></section>`
  }).join('')}</div>`
}

export function renderReferenceFactValue(label: string, value: string): string {
  const text = plainText(value)
  const name = /产品基础|产品名称/u.test(label) ? text.split(/[；;。]/u)[0] : /原料|工艺|产品属性|品牌背书|产品背书/u.test(label) ? text.split(/[，,；;。]/u)[0] : ''
  const emphasizeNumbers = (part: string): string => part.split(/([≥≤<>]?\s*\d+(?:\.\d+)?\s*(?:%|元|[gG]|克|袋|天|个月)|只选用嫩叶部分|未添加防腐剂|少盐少糖|免清洗|开袋即食|发酵全程可控|药品级净化车间)/u).map((piece, index) => index % 2 ? `<strong>${escape(piece)}</strong>` : escape(piece)).join('')
  return name ? `<strong>${escape(name)}</strong>${emphasizeNumbers(text.slice(name.length))}` : emphasizeNumbers(text)
}

export function renderReferenceAudienceStrategies(section: HtmlReportSection): string {
  const table = section.tables.find(table => table.context === '多平台核心人群TOP5')
  if (!table) return ''
  const column = (pattern: RegExp): number => table.headers.findIndex(header => pattern.test(header))
  const rank = column(/优先级/u), audience = column(/人群标签/u), traits = column(/占比|特征/u), motive = column(/决策动机/u), language = column(/内容语言/u)
  if (audience < 0) return ''
  return `<section class="reference-audience-strategies"><h3>多平台核心人群与内容策略</h3>${table.rows.slice(0, 5).map(row => `<article><div><span class="reference-audience-rank">${escape(row[rank] || '核心人群')}</span><strong class="reference-audience-name">${escape(row[audience] || '')}</strong>${traits >= 0 && row[traits] ? renderAudienceTraitTags(row[traits], true) : ''}</div><div class="reference-audience-copy"><h4>人群内容策略</h4>${motive >= 0 && row[motive] ? `<p><b>决策动机：</b><strong class="strategy-emphasis">${escape(row[motive])}</strong></p>` : ''}${language >= 0 && row[language] ? `<p><b>内容语言：</b><strong class="strategy-emphasis">${escape(row[language])}</strong></p>` : ''}<small>上述动机与内容建议为基于画像的待验证判断；不同维度和平台的数据不可直接相加。</small></div></article>`).join('')}</section>`
}

export function renderReferenceCover(model: HtmlReportModel, presentation: HtmlReportPresentation, productName: string, anchors: Map<string, string>): string {
  const cards = model.sections.filter(section => /^M[1-6]$/u.test(section.number)).map(section => {
    const number = Number(section.number.slice(1))
    let headline = referenceSectionSummary(section).headline
    let detail = excerpt(section)
    if (number === 2 && presentation.primaryAudience) {
      headline = presentation.primaryAudience.audience.split(/[｜|]/u)[0]
      detail = referenceSectionSummary(section).detail || presentation.primaryAudience.judgment
    }
    return `<a class="reference-summary-card" href="#${escape(anchors.get(section.number) || 'report-main')}" data-source-section="${section.number}"><span>${String(number).padStart(2, '0')} · ${MODULES[number - 1].label}</span><strong>${escape(shorten(headline, 32))}</strong><p>${escape(shorten(detail, 80))}</p></a>`
  }).join('')
  return `<header class="reference-cover"><p class="reference-eyebrow">产品经营报告 · 六大内容决策</p><h1>${escape(productName || model.title)}<br>短视频内容策略报告</h1><p class="reference-subtitle">围绕产品、人群、素材、卖点、用户声音和场景，找到下一步内容方向。</p><section class="reference-summary" aria-labelledby="reference-summary-title"><h2 id="reference-summary-title"><span>00</span> 核心结论</h2><div class="reference-summary-grid">${cards}</div><p class="reference-footnote">摘要来自本次报告资料。人群动机、内容场景与投放方向需结合实际表现继续验证。</p></section></header>`
}

export function renderReferenceModuleIntro(section: HtmlReportSection): string {
  const config = MODULES[Number(section.number.slice(1)) - 1]
  if (!config) return ''
  const summary = section.number === 'M3' ? '<p>自有与竞品素材分别统计；按框架、开头和表达方式对照，确定下一批补充方向。</p>' : `<p>${escape(excerpt(section))}</p>`
  return `<aside class="reference-module-intro" aria-label="${escape(section.title)}阅读与行动指南"><header><span>本模块阅读与行动建议</span><h3>${config.title}</h3>${summary}</header><div class="reference-intro-body"><div class="reference-intro-actions"><h4>什么时候用？解决什么问题？</h4><p>${config.use}</p><h4>团队现在怎么做</h4><ol>${config.actions.map(action => `<li>${action}</li>`).join('')}</ol></div><div class="reference-intro-deliverables"><section><h4>做完交付什么</h4><p>${config.deliverable}</p></section><section><h4>下一步怎么串联</h4><p>${config.next}</p></section></div></div></aside>${section.number === 'M3' ? `<div class="reference-material-samples"><b>素材样本</b>${renderReferenceMaterialCounts(section)}</div>` : ''}`
}

export function renderReferenceMaterialCounts(section: HtmlReportSection): string {
  // Only explicit totals from the overview; never sum overlapping framework clusters.
  const lines = section.markdown.split(/\r?\n/u).map(line => plainText(line).trim())
  const own = lines.find(line => /^(?:自有|自营)(?:视频|素材)\s*[：:]\s*\d+/u.test(line))
  const competitor = lines.find(line => /^竞品(?:视频|素材)\s*[：:]\s*\d+/u.test(line))
  const count = (line?: string): string => line?.match(/[：:]\s*(\d+)\s*条/u)?.[1] || '待确认'
  const source = lines.find(line => /^统计来源[：:]/u.test(line))
  return `<div class="reference-material-counts"><div><span>自有视频</span><strong>${count(own)}</strong><small>${count(own) === '待确认' ? '' : '条'}</small></div><div><span>竞品视频</span><strong>${count(competitor)}</strong><small>${count(competitor) === '待确认' ? '' : '条'}</small></div></div><div class="reference-material-scope">${[own, competitor, source].filter(Boolean).map(line => `<p>${escape(line!)}</p>`).join('') || '<p>报告未明确素材总数，需补充统计口径。</p>'}</div>`
}

export function renderReferenceMaterialCard(row: string[], headers: string[], index: number): string {
  const parts = plainText(row[0] || '素材方向').split(/[｜|]/u).map(part => part.trim()).filter(Boolean)
  const title = parts.length > 1 ? parts.slice(1, 3).join(' · ') : parts[0]
  const read = (pattern: RegExp): string => row[headers.findIndex(header => pattern.test(header))] || ''
  const audience = read(/主要人群/u), current = read(/自有现状/u)
  const direction = row[2] || '暂无分析'
  // Emphasize source wording only, without rewriting or dropping qualifications.
  const advice = plainText(direction).split(/(“[^”]+”)/u).map((part, i) => i % 2 ? `<strong>${escape(part)}</strong>` : escape(part)).join('')
  return `<article class="material-card"><header><span class="reference-material-dot" aria-label="第${index + 1}项">●</span><strong>${escape(title)}</strong></header><div class="reference-material-tags"><span class="material-framework"><b>框架类型</b> ${escape(parts.join('｜'))}</span><span class="material-basis"><b>${escape(headers[1] || '数据依据')}</b> ${escape(row[1] || '暂无数据依据')}</span>${audience ? `<span class="material-audience"><b>主要人群</b> ${escape(audience)}</span>` : ''}${current ? `<span class="material-audience"><b>自有现状</b> ${escape(current)}</span>` : ''}</div><p class="reference-material-advice"><b>${escape(headers[2] || '可复用方向')}：</b>${advice}</p></article>`
}

export function renderReferenceSellingGroups(section: HtmlReportSection): string {
  const table = section.tables.find(table => table.headers.some(h => /卖点维度/u.test(h)) && table.headers.some(h => /我方产品卖点/u.test(h)))
  if (!table) return ''
  const groups = new Map<string, string[][]>()
  for (const row of table.rows) groups.set(row[0], [...(groups.get(row[0]) || []), row])
  return `<figure class="visual-block reference-selling-groups"><figcaption><span class="reference-section-number">01</span> 产品卖点拆解：从产品特点到用户收益</figcaption><p class="visual-note">按需求分类阅读：加粗的是产品卖点，后面是对应的消费者买点。</p><nav class="reference-need-index" aria-label="四类需求">${[...groups.keys()].map((name, i) => `<a href="#reference-need-${i}" data-need-color="${i % 4}">${escape(name)}</a>`).join('')}</nav><div class="reference-needs-grid">${[...groups].map(([name, rows], i) => `<section class="reference-need-group" id="reference-need-${i}" data-need-color="${i % 4}"><h4>${escape(name)}</h4><ul>${rows.filter(row => row[1]).map(row => {
    const [selling, ...benefits] = row[1].split(/[｜|]/u)
    return `<li><span aria-hidden="true">✓</span><div><strong>${escape(selling)}</strong>${benefits.length ? `<span class="reference-need-benefit"><span aria-hidden="true">｜</span>${escape(benefits.join('｜'))}</span>` : ''}</div></li>`
  }).join('')}</ul></section>`).join('')}</div><p class="visual-note">来源：本报告产品事实与素材分析。具体证据和适用条件见下方完整推导。</p></figure>`
}

export function renderReferenceGenderOverview(plan: HtmlReportSectionPresentation): string {
  if (plan.sectionNumber !== 'M2') return ''
  // Only render complete, explicit gender distributions; never invent a remainder.
  const genders = plan.percentFacets.filter(facet => {
    const female = facet.items.find(item => /^(女|女性)$/u.test(item.label))
    const male = facet.items.find(item => /^(男|男性)$/u.test(item.label))
    return female && male && facet.items.length === 2 && Math.abs(female.value + male.value - 100) <= .1
  })
  if (!genders.length) return ''
  const majority = genders.every(facet => facet.items.find(item => /^(女|女性)$/u.test(item.label))!.value > 50) ? `${genders.length}个平台，女性均为主要成交人群` : '各平台成交人群的性别分布'
  return `<section class="reference-gender-overview"><span class="reference-eyebrow">人群画像 / 性别结构</span><h3>${majority}</h3><p>各平台独立统计，不合并计算。环形图展示各平台内部的男女占比。</p><div class="reference-gender-grid">${genders.map(facet => {
    const female = facet.items.find(item => /^(女|女性)$/u.test(item.label))!
    const male = facet.items.find(item => /^(男|男性)$/u.test(item.label))!
    return `<article><h4>${escape(facet.group)}</h4><div class="reference-gender-ring" role="img" aria-label="${escape(`${facet.group} 女性${female.display}，男性${male.display}`)}" style="--female-share:${female.value}%"><div><strong>${escape(female.display)}</strong><span>女性</span></div></div><p><span>●</span> 女性 ${escape(female.display)} <i>●</i> 男性 ${escape(male.display)}</p></article>`
  }).join('')}</div></section>`
}

export function renderReferenceClosing(): string {
  const steps = [
    ['核实产品事实', '整理资料与证据'], ['选择目标人群', '明确平台与场景'],
    ['锁定内容方向', '梳理需求、顾虑与缺口'], ['设计卖点证明', '对应利益、事实与画面'],
    ['制作并测试', '脚本、拍摄与投放'], ['复盘再生产', '记录结果，优化与复制']
  ]
  return `<section class="reference-closing" aria-labelledby="reference-closing-title"><div><span>从报告到执行</span><h2 id="reference-closing-title">把分析变成<br>内容生产闭环</h2><p>先选一个产品、一个平台、一个人群，完成一轮小批量测试，再根据结果决定下一批怎么做。</p></div><ol>${steps.map(([title, detail], i) => `<li><span>${String(i + 1).padStart(2, '0')}</span><strong>${title}</strong><p>${detail}</p></li>`).join('')}</ol><p class="reference-closing-note">内容方向及制作建议需结合实际业务和投放数据验证。</p></section>`
}
