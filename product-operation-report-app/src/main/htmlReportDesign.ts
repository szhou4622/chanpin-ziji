import { plainText, type HtmlReportDirection, type HtmlReportModel } from './htmlReportModel'
import type { ReportThemeTokens } from './htmlReportStyles'

export interface HtmlReportDesign {
  direction: HtmlReportDirection
  productName: string
  brandName: string
  variant: number
  reason: 'visual-brief' | 'product-category' | 'fallback'
  tokens: ReportThemeTokens
}

const sans = '"Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif'
const display = '"PingFang SC", "Microsoft YaHei UI", "Segoe UI", sans-serif'
const serif = '"Songti SC", "STSong", "SimSun", serif'

// Local system fonts and inline tokens keep the exported file entirely offline.
const BASE: ReportThemeTokens = {
  paper: 'oklch(97.5% .006 250)', paperAlt: 'oklch(96% .012 250)', surface: 'oklch(100% 0 0)',
  ink: 'oklch(27% .035 253)', inkSoft: 'oklch(40% .028 253)', muted: 'oklch(48% .022 253)',
  line: 'oklch(90% .012 250)', lineStrong: 'oklch(79% .024 250)',
  accent: 'oklch(48% .16 264)', accentStrong: 'oklch(39% .13 264)', accentSoft: 'oklch(95% .025 264)',
  series1: 'oklch(48% .16 264)', series2: 'oklch(64% .09 250)', series3: 'oklch(76% .06 240)', series4: 'oklch(49% .035 253)',
  warning: 'oklch(43% .09 65)', warningSoft: 'oklch(96% .025 65)',
  radius: '14px', shadow: '0 8px 32px oklch(27% .035 253 / .025)',
  fontDisplay: display, fontBody: sans, fontData: '"Segoe UI", Arial, sans-serif'
}

const FAMILY: Record<HtmlReportDirection, Partial<ReportThemeTokens>> = {
  'household-field-guide': { paper: 'oklch(97.4% .012 98)', paperAlt: 'oklch(95.5% .018 125)',
    accent: 'oklch(43% .075 152)', accentStrong: 'oklch(34% .065 152)', accentSoft: 'oklch(94.5% .03 142)',
    ink: 'oklch(26% .024 146)', inkSoft: 'oklch(38% .028 146)', muted: 'oklch(48% .025 142)',
    line: 'oklch(89% .016 125)', lineStrong: 'oklch(77% .026 125)', radius: '16px' },
  'restrained-catalogue': { paper: 'oklch(97.5% .009 58)', paperAlt: 'oklch(95% .018 34)',
    accent: 'oklch(45% .075 14)', accentStrong: 'oklch(35% .065 14)', accentSoft: 'oklch(95% .022 14)',
    ink: 'oklch(25% .019 22)', inkSoft: 'oklch(39% .028 22)', muted: 'oklch(48% .024 22)',
    line: 'oklch(90% .014 34)', lineStrong: 'oklch(78% .024 34)', radius: '2px', fontDisplay: serif },
  'material-editorial': { paper: 'oklch(97% .017 78)', paperAlt: 'oklch(94.5% .024 72)',
    accent: 'oklch(43% .065 57)', accentStrong: 'oklch(33% .045 57)', accentSoft: 'oklch(94% .032 72)',
    ink: 'oklch(26% .023 57)', inkSoft: 'oklch(39% .026 57)', muted: 'oklch(48% .028 57)',
    line: 'oklch(89% .022 72)', lineStrong: 'oklch(77% .03 72)', radius: '8px', fontDisplay: serif },
  'technical-workbench': { accent: 'oklch(45% .14 257)', accentStrong: 'oklch(34% .11 257)',
    accentSoft: 'oklch(95% .022 257)', radius: '4px', fontDisplay: 'Bahnschrift, "Microsoft YaHei UI", sans-serif',
    fontData: '"Cascadia Mono", Consolas, monospace' },
  'calm-evidence': { paper: 'oklch(98% .006 190)', paperAlt: 'oklch(96% .016 187)',
    accent: 'oklch(43% .075 191)', accentStrong: 'oklch(33% .06 191)', accentSoft: 'oklch(95% .03 191)', radius: '18px' },
  'energetic-social': { paper: 'oklch(98% .01 80)', paperAlt: 'oklch(95.5% .025 66)',
    accent: 'oklch(49% .15 35)', accentStrong: 'oklch(38% .12 35)', accentSoft: 'oklch(95% .035 50)', radius: '20px' },
  'utilitarian-decision-brief': { accent: 'oklch(39% .055 242)', accentStrong: 'oklch(29% .045 242)',
    accentSoft: 'oklch(95% .014 242)', radius: '4px', fontData: 'Consolas, monospace' },
  'neutral-evidence': {}
}

function identityText(model: HtmlReportModel): { productName: string; brandName: string; category: string } {
  const product = model.sections.find(section => section.number === 'M1')
  const rows = product?.tables.flatMap(table => table.rows) || []
  // Route on the merchant's product identity only. Competitors, audience purchase
  // preferences, claimed ingredients and comments cannot change the design family.
  const identity = rows.filter(row => /^(?:\d+[.、\s]*)?(?:产品基础|产品名称|商品名称|产品|名称|品类|产品类型|所属品类|品牌名称|品牌)$/u.test(plainText(row[0] || '')))
  const category = identity.map(row => plainText(row[1] || '')).join('；')
  const nameRow = identity.find(row => /产品基础|产品名称|商品名称|^产品$|^名称$/u.test(row[0]))
  const suppliedTitle = model.title.replace(/\s*(?:产品内容策略报告|产品与内容经营报告|产品经营报告)\s*$/u, '').trim()
  const name = plainText(nameRow?.[1] || suppliedTitle).split(/[；;。\n]/u)[0].replace(/^(?:产品名称|商品名称|名称)\s*[：:]\s*/u, '')
  const brandRow = identity.find(row => /^(品牌|品牌名称)$/u.test(row[0]))
  const brand = plainText(brandRow?.[1] || category.match(/(?:品牌名称|品牌)\s*[：:]?\s*([^；;，,。]+)/u)?.[1] || '')
  return { productName: name.length <= 72 && !/^(无|未知|需补充|未提供|待确认)$/u.test(name) ? name : '',
    brandName: brand.length <= 30 && !/^(无|未知|需补充|未提供|待确认)$/u.test(brand) ? brand : '', category }
}

export function resolveHtmlReportDesign(model: HtmlReportModel): HtmlReportDesign {
  const identity = identityText(model)
  let direction = model.brief.designDirection
  let reason: HtmlReportDesign['reason'] = model.brief.evidenceConfidence === 'insufficient' ? 'fallback' : 'visual-brief'
  if (reason === 'fallback') {
    const rules: Array<[HtmlReportDirection, RegExp]> = [
      ['utilitarian-decision-brief', /工业|企业软件|SaaS|机床|工业设备/iu],
      ['household-field-guide', /酸菜|酱腌菜|食品|饮料|咖啡|茶叶|鸡蛋|牛奶|糕点|零食|调味|果汁|粮油|牛肉|水果|饮品/u],
      ['restrained-catalogue', /护肤|面霜|精华液|洁面|面膜|彩妆|口红|香水|洗发|美容仪|珠宝|首饰/u],
      ['material-editorial', /枕头|床垫|床品|床单|家纺|沙发|家具|香薰|灯具|窗帘|收纳|厨具|餐具|家居/u],
      ['technical-workbench', /耳机|手机|电脑|键盘|充电|路由器|音箱|打印机|显示器|传感器|相机/u],
      ['calm-evidence', /保健品|膳食补充|维生素|营养补充|蛋白粉|医用|医疗器械/u],
      ['energetic-social', /玩具|潮玩|文创|游戏|宠物|盲盒|运动|户外/u]
    ]
    const matches = rules.filter(([, rule]) => rule.test(identity.category))
    if (matches.length === 1) { direction = matches[0][0]; reason = 'product-category' }
  }
  let seed = 0
  for (const char of (identity.brandName || identity.productName).replace(/\s+/gu, '')) seed = (seed * 31 + char.charCodeAt(0)) >>> 0
  const variant = identity.brandName || identity.productName ? seed % 3 : 0
  const tokens = { ...BASE, ...FAMILY[direction] }
  // A stable brand signature provides restrained palette/layout variation within
  // a family; it never represents a supplied brand colour or a factual claim.
  if (variant === 1) tokens.accentSoft = `color-mix(in oklch, ${tokens.accentSoft} 68%, ${tokens.surface})`
  if (variant === 2) tokens.paper = tokens.surface
  tokens.series1 = tokens.accent
  tokens.series2 = `color-mix(in oklch, ${tokens.accent} 72%, ${tokens.surface})`
  tokens.series3 = `color-mix(in oklch, ${tokens.accent} 38%, ${tokens.surface})`
  tokens.series4 = tokens.inkSoft
  return { ...identity, direction, reason, variant, tokens }
}

export function renderModernReportStyles(): string {
  return `
  /* Hallmark · macrostructure: Long Document · genre: modern-minimal
     Merchant families share evidence semantics; product identity selects typography, palette and cover rhythm. */
  body[data-report-format="modules"] {
    --content-pad: clamp(24px, 3.2vw, 48px);
    --space-xs: 4px; --space-sm: 8px; --space-md: 16px; --space-lg: 24px; --space-xl: 32px; --space-2xl: 48px;
    --text-display: clamp(30px, 3.4vw, 46px); --text-title: clamp(21px, 2vw, 27px);
    --ease-out: cubic-bezier(.16, 1, .3, 1);
    background: var(--paper); font-size: 14px; line-height: 1.8;
  }
  .report-masthead { width: min(1480px, calc(100% - 64px)); margin: 0 auto; min-height: 80px; display: flex; align-items: center; justify-content: space-between; gap: 20px; border-bottom: 1px solid var(--line); }
  .report-masthead__brand { display: flex; align-items: baseline; flex-wrap: wrap; gap: 12px; }
  .report-masthead__brand strong { font: 650 18px/1.4 var(--font-display); letter-spacing: -.03em; }
  .report-masthead__brand span, .report-masthead > span { color: var(--muted); font-size: 12px; }
  body[data-report-format="modules"] .shell { grid-template-columns: 188px minmax(0, 1fr); gap: 36px; width: min(1480px, calc(100% - 64px)); margin: 32px auto 64px; }
  body[data-report-format="modules"] .toc { top: 28px; padding: 12px 0; background: transparent; border: 0; border-radius: 0; }
  body[data-report-format="modules"] .toc-title { margin: 0 12px 18px; font-size: 12px; font-weight: 500; color: var(--muted); }
  body[data-report-format="modules"] .toc a { display: flex; align-items: center; gap: 10px; padding: 11px 12px; margin: 4px 0; font-size: 13px; border-radius: 6px; color: var(--ink-soft); white-space: nowrap; }
  .toc-no { font: 500 11px/1 var(--font-data); color: var(--muted); }
  body[data-report-format="modules"] .toc a { max-width: 100%; }
  body[data-report-format="modules"] .toc a > span:last-child { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
  body[data-report-format="modules"] .toc a:hover { background: var(--accent-soft); color: var(--accent-strong); }
  .toc-note { margin: 24px 12px 0; padding-top: 20px; border-top: 1px solid var(--line); color: var(--muted); font-size: 11px; line-height: 1.8; }
  body[data-report-format="modules"] .report { border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--page-shadow); }
  body[data-report-format="modules"] .story-stat-hero { min-height: 0; padding: 32px var(--content-pad) 0; border: 0; background: var(--surface); }
  body[data-report-format="modules"] .story-stat-hero__meta { padding: 0 0 24px; border: 0; font-size: 11px; color: var(--muted); }
  body[data-report-format="modules"] .story-stat-hero__grid { grid-template-columns: minmax(0, 1.4fr) minmax(0, .8fr); gap: 40px; min-height: 0; padding: 12px 0 32px; align-items: center; }
  body[data-report-format="modules"] .hero-copy { order: 1; }
  body[data-report-format="modules"] .hero-copy h1 { max-width: 18em; font-size: var(--text-display); line-height: 1.35; letter-spacing: -.045em; font-weight: 650; }
  .hero-report-label { margin: 0 0 12px; font-size: 12px; font-weight: 500; color: var(--accent-strong); }
  body[data-report-format="modules"] .hero-thesis { margin-top: 20px; font-size: 15px; line-height: 1.9; color: var(--ink-soft); }
  body[data-report-format="modules"] .hero-figure { order: 2; padding: 24px; background: var(--accent-soft); border-radius: calc(var(--radius) * .7); border: 0; border-left: 3px solid var(--accent); }
  body[data-report-format="modules"] .hero-figure small { order: -1; margin: 0 0 12px; font-size: 11px; color: var(--accent-strong); line-height: 1.7; }
  body[data-report-format="modules"] .hero-figure strong { font: 650 clamp(24px, 2.2vw, 32px)/1.5 var(--font-display); letter-spacing: -.03em; color: var(--ink); }
  body[data-report-format="modules"] .hero-figure span { margin-top: 10px; font-size: 13px; font-weight: 500; color: var(--ink-soft); line-height: 1.75; }
  body[data-report-format="modules"] .signal-strip { border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
  body[data-report-format="modules"] .signal-strip > div { padding: 24px 20px; border-color: var(--line); }
  body[data-report-format="modules"] .signal-strip > div:first-child { padding-left: 0; }
  body[data-report-format="modules"] .signal-strip strong { font: 550 clamp(27px, 2.7vw, 36px)/1.2 var(--font-data); color: var(--accent-strong); letter-spacing: -.035em; font-variant-numeric: tabular-nums; }
  body[data-report-format="modules"] .signal-strip span { margin-top: 8px; font-size: 12px; font-weight: 500; }
  body[data-report-format="modules"] .signal-strip small { font-size: 11px; }
  body[data-report-format="modules"] .decision-dashboard { padding: 32px var(--content-pad) 36px; background: var(--surface); }
  body[data-report-format="modules"] .decision-dashboard__head { display: block; margin-bottom: 16px; }
  body[data-report-format="modules"] .decision-dashboard__head h2 { margin: 0; font-size: 19px; font-weight: 650; }
  body[data-report-format="modules"] .decision-dashboard__head p { max-width: 70em; margin: 8px 0 0; font-size: 11px; color: var(--muted); }
  body[data-report-format="modules"] .priority-lanes { display: block; border: 0; }
  body[data-report-format="modules"] .priority-lane { display: grid; grid-template-columns: 72px minmax(0, .8fr) minmax(0, 1.2fr); align-items: start; gap: 20px; padding: 18px 0; border: 0; border-bottom: 1px solid var(--line); }
  body[data-report-format="modules"] .priority-lane:last-child { border-bottom: 0; }
  body[data-report-format="modules"] .priority-lane__rank { margin: 2px 0 0; padding: 3px 6px; background: var(--paper-alt); color: var(--ink-soft); font: 500 10px/1.6 var(--font-body); text-align: center; border-radius: 4px; }
  body[data-report-format="modules"] .priority-lane:first-child .priority-lane__rank { color: var(--accent-strong); background: var(--accent-soft); }
  body[data-report-format="modules"] .priority-lane h3 { margin: 0; font-size: 14px; font-weight: 600; line-height: 1.75; }
  body[data-report-format="modules"] .priority-lane p { margin: 0; font-size: 12px; line-height: 1.8; color: var(--muted); }
  body[data-report-format="modules"] .report-body { padding: 0 var(--content-pad) 36px; }
  body[data-report-format="modules"] .report-section { padding-top: 40px; margin-bottom: 8px; border-top: 1px solid var(--line); }
  body[data-report-format="modules"] .report-section > h2 { margin: 0 0 28px; padding: 0; border: 0; font-size: var(--text-title); font-weight: 650; line-height: 1.5; letter-spacing: -.025em; scroll-margin-top: 24px; }
  body[data-report-format="modules"] .report-section h3 { font-weight: 600; }
  body[data-report-format="modules"] .visual-block { margin: 0 0 24px; }
  body[data-report-format="modules"] .visual-block > figcaption { padding: 0; margin-bottom: 16px; font-size: 13px; font-weight: 600; color: var(--ink-soft); border: 0; }
  body[data-report-format="modules"] .visual-note { max-width: none; margin: 16px 0; font-size: 11px; line-height: 1.8; color: var(--muted); }
  body[data-report-format="modules"] .fact-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 28px; border-top: 1px solid var(--line); }
  body[data-report-format="modules"] .fact-item { display: grid; grid-template-columns: 24px minmax(68px, .5fr) minmax(0, 1.5fr); gap: 12px; padding: 18px 0; background: transparent; border: 0; border-bottom: 1px solid var(--line); align-items: start; }
  body[data-report-format="modules"] .fact-item b { color: var(--accent); font: 500 10px/2 var(--font-data); }
  body[data-report-format="modules"] .fact-item span { color: var(--muted); font-size: 11px; }
  body[data-report-format="modules"] .fact-item strong { font-size: 12px; line-height: 1.9; font-weight: 500; }
  body[data-report-format="modules"] .profile-platform-index { margin-bottom: 16px; padding: 0; border: 0; font-size: 11px; }
  body[data-report-format="modules"] .profile-platform-index span { background: var(--paper-alt); color: var(--ink-soft); border: 0; border-radius: 4px; }
  body[data-report-format="modules"] .profile-board { grid-template-columns: repeat(var(--profile-columns, 3), minmax(0, 1fr)); gap: 20px; }
  body[data-report-format="modules"] .profile-panel { padding: 20px; border: 1px solid var(--line); border-radius: calc(var(--radius) * .7); background: var(--surface); min-width: 0; }
  body[data-report-format="modules"] .profile-panel__head { display: block; padding: 0 0 16px; border-bottom: 1px solid var(--line); margin-bottom: 20px; }
  body[data-report-format="modules"] .profile-panel__head > span { font-size: 10px; color: var(--muted); }
  body[data-report-format="modules"] .profile-panel__head h3 { margin: 4px 0 0; font-size: 16px; }
  body[data-report-format="modules"] .profile-kpis { gap: 16px; grid-template-columns: repeat(2, minmax(0, 1fr)); background: transparent; }
  body[data-report-format="modules"] .profile-kpi { padding: 0; background: transparent; border: 0; }
  body[data-report-format="modules"] .profile-kpi strong { font-size: 25px; font-weight: 550; }
  body[data-report-format="modules"] .profile-facets { gap: 24px; }
  body[data-report-format="modules"] .bar-facet h4 { font-size: 12px; font-weight: 600; margin-bottom: 14px; }
  body[data-report-format="modules"] .bar-label { gap: 8px; margin-bottom: 6px; font-size: 11px; }
  body[data-report-format="modules"] .bar-label strong { font-size: 11px; font-weight: 550; }
  body[data-report-format="modules"] .bar-track { height: 5px; min-height: 0; background: var(--paper-alt); border-radius: 3px; overflow: hidden; }
  body[data-report-format="modules"] .bar-track span { border-radius: 3px; }
  body[data-report-format="modules"] .method-playbooks { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 22px; }
  body[data-report-format="modules"] .method-playbook { padding: 0; border: 0; background: transparent; }
  body[data-report-format="modules"] .method-playbook > header { display: block; padding: 12px 0; border: 0; border-top: 2px solid var(--accent); margin-bottom: 4px; }
  body[data-report-format="modules"] .method-playbook > header span { color: var(--accent-strong); font-size: 13px; font-weight: 600; }
  body[data-report-format="modules"] .method-playbook > header strong { display: block; margin-top: 4px; font-size: 10px; color: var(--muted); font-weight: 400; }
  body[data-report-format="modules"] .material-card-list { gap: 0; }
  body[data-report-format="modules"] .material-card { padding: 20px 0; border: 0; border-bottom: 1px solid var(--line); background: transparent; }
  body[data-report-format="modules"] .material-card h4 { font-size: 13px; font-weight: 600; line-height: 1.8; }
  body[data-report-format="modules"] .material-card p { font-size: 12px; line-height: 1.8; }
  body[data-report-format="modules"] .material-card > span { color: var(--muted); font-weight: 500; font-size: 10px; }
  body[data-report-format="modules"] .selling-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
  body[data-report-format="modules"] .selling-item { padding: 20px; border: 0; border-radius: calc(var(--radius) * .7); background: var(--paper-alt); }
  body[data-report-format="modules"] .selling-item span { font-size: 11px; font-weight: 500; color: var(--accent-strong); }
  body[data-report-format="modules"] .selling-item strong { margin-top: 12px; font-size: 15px; font-weight: 600; }
  body[data-report-format="modules"] .selling-item p { font-size: 12px; line-height: 1.9; }
  body[data-report-format="modules"] .selling-item.is-missing { border: 1px dashed var(--line-strong); background: var(--surface); }
  body[data-report-format="modules"] .ordinal-list { padding: 0; border: 0; }
  body[data-report-format="modules"] .ordinal-item { border-bottom: 1px solid var(--line); padding: 18px 0; }
  body[data-report-format="modules"] .ordinal-item > span { font-size: 14px; font-weight: 550; }
  body[data-report-format="modules"] .ordinal-item:nth-child(-n+3) { background: transparent; }
  body[data-report-format="modules"] .voc-board { gap: 24px; }
  body[data-report-format="modules"] .voc-group { padding: 20px; border: 1px solid var(--line); border-radius: calc(var(--radius) * .7); }
  body[data-report-format="modules"] .voc-group > header { padding: 0 0 14px; border-bottom: 1px solid var(--line); }
  body[data-report-format="modules"] .voc-group > header strong { font-size: 15px; font-weight: 600; }
  body[data-report-format="modules"] .voc-item { padding: 16px 0; }
  body[data-report-format="modules"] .voc-item blockquote { background: var(--paper-alt); border-left: 2px solid var(--line-strong); font-size: 12px; }
  body[data-report-format="modules"] .voc-metrics span { background: var(--paper-alt); border: 0; border-radius: 4px; }
  body[data-report-format="modules"] .audience-routes { gap: 20px; }
  body[data-report-format="modules"] .audience-route { padding: 20px; border: 1px solid var(--line); border-radius: calc(var(--radius) * .7); background: var(--surface); }
  body[data-report-format="modules"] .audience-route__path > div { background: var(--paper-alt); border: 0; border-radius: 6px; padding: 16px; }
  body[data-report-format="modules"] .audience-route__path > div:last-child { background: var(--accent-soft); }
  body[data-report-format="modules"] .audience-evidence span { padding: 10px 0; border: 0; font-size: 11px; }
  body[data-report-format="modules"] .evidence-disclosure { margin-top: 20px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); }
  body[data-report-format="modules"] .evidence-disclosure summary { background: var(--paper-alt); padding: 14px 18px; font-size: 12px; font-weight: 500; }
  body[data-report-format="modules"] .evidence-disclosure[open] summary { border-bottom: 1px solid var(--line); }
  body[data-report-format="modules"] th { font-size: 11px; font-weight: 600; background: var(--paper-alt); }
  body[data-report-format="modules"] td { font-size: 12px; line-height: 1.9; }
  body[data-report-format="modules"] .report-ai-disclaimer { margin-top: 40px; }
  body[data-report-format="modules"] .report-ai-disclaimer blockquote { margin: 0; padding: 20px 0 0; border: 0; border-top: 1px solid var(--line); background: transparent; color: var(--muted); font-size: 11px; }

  /* Shared metric grammar, distinct merchant cover and typography. */
  body[data-report-style="household-field-guide"] .story-stat-hero { background: var(--paper); }
  body[data-report-style="household-field-guide"] .hero-figure { border-left: 0; border-top: 3px solid var(--accent); }
  body[data-report-style="restrained-catalogue"] .hero-copy h1,
  body[data-report-style="material-editorial"] .hero-copy h1 { font-weight: 500; letter-spacing: .025em; line-height: 1.5; }
  body[data-report-style="restrained-catalogue"] .story-stat-hero__grid { grid-template-columns: minmax(0, 1fr); gap: 24px; padding-top: 24px; }
  body[data-report-style="restrained-catalogue"] .hero-figure { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); column-gap: 20px; padding: 20px 0; border: 0; border-block: 1px solid var(--line); border-radius: 0; background: transparent; }
  body[data-report-style="restrained-catalogue"] .hero-figure small { grid-column: 1 / -1; }
  body[data-report-style="restrained-catalogue"] .hero-copy { max-width: 760px; }
  body[data-report-style="restrained-catalogue"] .fact-grid { grid-template-columns: minmax(0, 1fr); }
  body[data-report-style="restrained-catalogue"] .selling-item { padding: 24px 0; background: transparent; border-top: 1px solid var(--line-strong); border-radius: 0; }
  body[data-report-style="material-editorial"] .story-stat-hero { background: var(--paper); }
  body[data-report-style="material-editorial"] .hero-figure { border-radius: 0; background: transparent; border-left: 1px solid var(--line-strong); }
  body[data-report-style="material-editorial"] .fact-item { padding-block: 24px; }
  body[data-report-style="material-editorial"] .selling-item { border-left: 2px solid var(--line-strong); border-radius: 0; }
  body[data-report-style="technical-workbench"] .story-stat-hero,
  body[data-report-style="utilitarian-decision-brief"] .story-stat-hero { border-top: 4px solid var(--accent); }
  body[data-report-style="technical-workbench"] .hero-figure,
  body[data-report-style="utilitarian-decision-brief"] .hero-figure { border: 1px solid var(--line-strong); background: var(--paper-alt); }
  body[data-report-style="technical-workbench"] .fact-item strong { font-family: var(--font-body); }
  body[data-report-style="technical-workbench"] .profile-panel__head { border-top: 2px solid var(--accent); padding-top: 12px; }
  body[data-report-style="calm-evidence"] .hero-figure { border: 0; border-radius: 20px; }
  body[data-report-style="energetic-social"] .hero-copy h1 { font-weight: 800; letter-spacing: -.04em; }
  body[data-report-style="energetic-social"] .selling-item { border-radius: 18px; }
  body[data-brand-variant="1"] .story-stat-hero__grid { grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr); }
  body[data-brand-variant="2"] .story-stat-hero__grid { grid-template-columns: minmax(0, 1fr); gap: 20px; }
  body[data-brand-variant="2"] .hero-figure { display: block; padding: 18px 24px; }
  body[data-brand-variant="2"] .hero-figure small { display: block; }
  body[data-brand-variant="2"] .hero-figure span { display: inline-block; margin-left: 24px; }

  /* Native radio selection makes the word cloud usable offline, without scripts. */
  .material-insight-cloud.keyword-panel { padding: 24px; margin-bottom: 28px; background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); }
  .material-insight-cloud > header { display: flex; align-items: baseline; justify-content: space-between; gap: 20px; padding: 0; border: 0; }
  .material-insight-cloud > header small { color: var(--muted); font-size: 11px; }
  .material-insight-cloud h3 { margin: 4px 0 0; font-size: 19px; line-height: 1.5; font-weight: 650; }
  .cloud-scope { white-space: nowrap; color: var(--accent-strong); font-size: 11px; border: 1px solid var(--line); border-radius: 4px; padding: 4px 8px; }
  .material-insight-summary { display: flex; flex-wrap: wrap; gap: 12px 24px; margin: 20px 0 24px; padding: 14px 0; border-block: 1px solid var(--line); }
  .material-insight-summary span { color: var(--muted); font-size: 11px; }
  .material-insight-summary strong { margin-left: 6px; color: var(--ink); font: 600 16px/1 var(--font-data); }
  .cloud-explorer { position: relative; display: grid; grid-template-columns: minmax(0, 1fr) minmax(180px, .4fr); gap: 28px; }
  .cloud-visual { min-width: 0; }
  .cloud-axis-note { display: flex; gap: 8px; justify-content: space-between; margin: 0 0 12px; color: var(--muted); font-size: 10px; }
  .material-insight-words.word-cloud { min-height: 280px; padding: 20px 12px; gap: 12px 14px; background: var(--paper-alt); border: 0; border-radius: calc(var(--radius) * .7); align-content: center; }
  .material-insight-words .word-cloud__item { position: relative; display: inline-flex; align-items: baseline; gap: 5px; max-width: 100%; padding: 5px 7px; border-radius: 5px; cursor: pointer; color: var(--ink-soft); font-size: var(--cloud-size); line-height: 1.5; white-space: nowrap; }
  .material-insight-words .word-cloud__item b { min-width: 0; font-family: var(--font-display); font-size: inherit; line-height: 1.5; font-weight: 550; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; letter-spacing: -.025em; }
  .material-insight-words .word-cloud__item small { flex-shrink: 0; color: var(--muted); font-size: 9px; font-weight: 400; }
  .material-insight-words .word-cloud__item[data-cloud-emphasis="high"] { color: var(--accent-strong); }
  .material-insight-words .word-cloud__item:hover { background: var(--surface); }
  .material-insight-words .word-cloud__item:has(input:checked) { color: var(--accent-strong); background: var(--surface); box-shadow: 0 0 0 1px var(--line-strong); }
  .cloud-control { position: absolute; width: 1px; height: 1px; left: 50%; top: 50%; opacity: 0; margin: 0; }
  .word-cloud__item:has(input:focus-visible), .cloud-ranking:has(a:focus-visible) { outline: 2px solid var(--accent); outline-offset: 3px; }
  .cloud-rankings { padding-left: 24px; border-left: 1px solid var(--line); min-width: 0; }
  .cloud-rankings h4 { margin: 0 0 8px; font-size: 12px; font-weight: 600; }
  .cloud-rankings > p { margin: 0 0 18px; color: var(--muted); font-size: 10px; }
  .cloud-ranking { display: block; padding: 10px 0; }
  .cloud-ranking > div { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; font-size: 11px; }
  .cloud-ranking > div span { color: var(--ink-soft); min-width: 0; }
  .cloud-ranking > div strong { white-space: nowrap; font: 600 13px/1 var(--font-data); }
  .cloud-rank-track { display: block; height: 4px; margin-top: 8px; border-radius: 2px; background: var(--paper-alt); }
  .cloud-rank-track i { display: block; height: 100%; width: var(--frequency-width); background: var(--accent); border-radius: inherit; }
  .cloud-evidence { grid-column: 1 / -1; min-width: 0; border-top: 1px solid var(--line); padding-top: 20px; }
  .cloud-evidence-panel { display: none; }
  .cloud-evidence-panel > header { display: flex; gap: 16px; justify-content: space-between; align-items: baseline; margin-bottom: 12px; }
  .cloud-evidence-panel h4 { margin: 0; font: 600 16px/1.6 var(--font-display); color: var(--accent-strong); }
  .cloud-evidence-panel > header > span { color: var(--muted); font-size: 11px; }
  .cloud-evidence-panel > p { margin: 8px 0; font-size: 11px; color: var(--muted); }
  .cloud-evidence-panel details { border: 0; border-top: 1px solid var(--line); padding: 12px 0; }
  .cloud-evidence-panel summary { cursor: pointer; color: var(--ink-soft); font-size: 12px; line-height: 1.9; }
  .cloud-evidence-panel details small { display: block; font-size: 11px; margin-top: 12px; color: var(--muted); overflow-wrap: anywhere; }
  .cloud-evidence-panel details blockquote { margin: 12px 0; padding: 12px 16px; background: var(--paper-alt); border-left: 2px solid var(--line-strong); font-size: 12px; }
  .cloud-footnote { padding-top: 12px; border-top: 1px solid var(--line); }
  @supports not selector(:has(*)) {
    .cloud-evidence-panel { display: block; margin-bottom: 24px; }
    .cloud-axis-note { display: none; }
  }

  @media screen and (max-width: 1200px) {
    body[data-report-format="modules"] .shell { grid-template-columns: 160px minmax(0, 1fr); gap: 24px; width: calc(100% - 40px); }
    .report-masthead { width: calc(100% - 40px); }
    body[data-report-format="modules"] .profile-board { grid-template-columns: minmax(0, 1fr); }
    body[data-report-format="modules"] .profile-facets { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    body[data-report-format="modules"] .profile-kpis { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    body[data-report-format="modules"] .fact-grid { grid-template-columns: minmax(0, 1fr); }
    .cloud-explorer { grid-template-columns: minmax(0, 1fr); }
    .cloud-rankings { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0 20px; padding: 0; border: 0; }
    .cloud-rankings h4, .cloud-rankings > p { grid-column: 1 / -1; }
    .cloud-rankings > p { margin-bottom: 4px; }
    .material-insight-words.word-cloud { min-height: 240px; }
  }
  @media screen and (max-width: 900px) {
    body[data-report-format="modules"] .shell { grid-template-columns: minmax(0, 1fr); display: block; width: calc(100% - 32px); margin-top: 16px; }
    body[data-report-format="modules"] .toc { position: static; display: flex; flex-wrap: wrap; gap: 4px 8px; padding: 0 0 16px; max-height: none; }
    body[data-report-format="modules"] .toc-title, .toc-note { display: none; }
    body[data-report-format="modules"] .toc a { margin: 0; padding: 7px 10px; background: var(--surface); border: 1px solid var(--line); font-size: 12px; }
    body[data-report-format="modules"] .toc-no { font-size: 10px; }
    body[data-report-format="modules"] .chapter-index { display: none; }
    body[data-report-format="modules"] .method-playbooks { grid-template-columns: minmax(0, 1fr); gap: 24px; }
    body[data-report-format="modules"] .material-card-list { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 20px; }
    body[data-report-format="modules"] .voc-board { grid-template-columns: minmax(0, 1fr); }
  }
  @media screen and (max-width: 600px) {
    .report-masthead { width: calc(100% - 32px); min-height: 68px; }
    .report-masthead > span { display: none; }
    .report-masthead__brand { gap: 8px; }
    .report-masthead__brand strong { font-size: 16px; }
    body[data-report-format="modules"] { --content-pad: 20px; --text-display: 30px; --text-title: 21px; }
    body[data-report-format="modules"] .shell { width: calc(100% - 24px); }
    body[data-report-format="modules"] .story-stat-hero { padding: 24px var(--content-pad) 0; }
    body[data-report-format="modules"] .story-stat-hero__meta { padding-bottom: 12px; gap: 4px; }
    body[data-report-format="modules"] .story-stat-hero__grid { grid-template-columns: minmax(0, 1fr); gap: 20px; padding: 12px 0 24px; }
    body[data-report-format="modules"] .hero-figure { display: block; padding: 18px; }
    body[data-report-format="modules"] .hero-figure strong { font-size: 24px; }
    body[data-report-format="modules"] .hero-figure span { display: block; margin-left: 0; }
    body[data-report-format="modules"] .hero-thesis { font-size: 13px; }
    body[data-report-format="modules"] .signal-strip { grid-template-columns: minmax(0, 1fr); border-bottom: 0; }
    body[data-report-format="modules"] .signal-strip > div { display: grid; grid-template-columns: minmax(0, 1fr) auto; column-gap: 16px; padding: 16px 0; border-right: 0; border-bottom: 1px solid var(--line); }
    body[data-report-format="modules"] .signal-strip strong { grid-column: 2; grid-row: 1 / 3; align-self: center; font-size: 28px; }
    body[data-report-format="modules"] .signal-strip span { margin: 0; grid-row: 1; }
    body[data-report-format="modules"] .signal-strip small { margin: 2px 0 0; grid-column: 1; }
    body[data-report-format="modules"] .decision-dashboard { padding: 28px var(--content-pad); }
    body[data-report-format="modules"] .priority-lane { grid-template-columns: minmax(0, 1fr); gap: 8px; }
    body[data-report-format="modules"] .priority-lane__rank { justify-self: start; }
    body[data-report-format="modules"] .priority-lane p { grid-column: auto; }
    body[data-report-format="modules"] .report-body { padding-inline: var(--content-pad); }
    body[data-report-format="modules"] .report-section { padding-top: 28px; }
    body[data-report-format="modules"] .report-section > h2 { margin-bottom: 20px; }
    body[data-report-format="modules"] .fact-item { grid-template-columns: 20px minmax(0, 1fr); gap: 6px 10px; }
    body[data-report-format="modules"] .fact-item strong { grid-column: 2; }
    body[data-report-format="modules"] .profile-panel { padding: 16px; }
    body[data-report-format="modules"] .profile-facets { grid-template-columns: minmax(0, 1fr); }
    body[data-report-format="modules"] .profile-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    body[data-report-format="modules"] .material-card-list, body[data-report-format="modules"] .selling-grid { grid-template-columns: minmax(0, 1fr); }
    body[data-report-format="modules"] .audience-route { grid-template-columns: minmax(0, 1fr); padding: 16px; }
    body[data-report-format="modules"] .audience-route__path, body[data-report-format="modules"] .audience-evidence { grid-template-columns: minmax(0, 1fr); grid-column: 1; }
    body[data-report-format="modules"] .route-arrow { transform: rotate(90deg); }
    .material-insight-cloud.keyword-panel { padding: 16px; }
    .material-insight-cloud > header { display: block; }
    .cloud-scope { display: inline-block; margin-top: 8px; }
    .material-insight-summary { gap: 8px 16px; }
    .material-insight-words.word-cloud { padding: 16px 8px; gap: 10px 4px; min-height: 240px; }
    .material-insight-words .word-cloud__item { font-size: min(var(--cloud-size), 24px); }
    .cloud-rankings { grid-template-columns: minmax(0, 1fr); }
    .cloud-evidence-panel > header { display: block; }
    .cloud-evidence-panel > header > span { display: block; margin-top: 6px; }
    .cloud-axis-note { display: block; }
    .cloud-axis-note span { display: block; }
  }
  @media print {
    .report-masthead, .toc-note, .cloud-rankings, .cloud-axis-note, .cloud-evidence { display: none !important; }
    .cloud-explorer { display: block; }
    .material-insight-cloud.keyword-panel { break-inside: auto; padding: 12px; }
    .material-insight-words.word-cloud { min-height: 0; }
    .material-insight-print-copy { display: block; }
    body[data-report-format="modules"] .shell { display: block; width: 100%; margin: 0; }
    body[data-report-format="modules"] .report { border: 0; border-radius: 0; box-shadow: none; }
    body[data-report-format="modules"] .hero-copy h1 { font-size: 28pt; }
    body[data-report-format="modules"] .story-stat-hero { padding-inline: 0; }
    body[data-report-format="modules"] .decision-dashboard, body[data-report-format="modules"] .report-body { padding-inline: 0; }
  }
  `
}
