import { strict as assert } from 'node:assert'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { basename, join, resolve } from 'node:path'
import { app, BrowserWindow } from 'electron'
import { merchantDesignFixture, cloudDesignFixture } from './fixtures/report-design'
import {
  buildHtmlReportPresentation,
  markdownToHtmlDocument,
  parseHtmlReportModel
} from '../src/main/htmlReport'

interface SavedReportProject {
  reportMarkdown?: unknown
  project?: SavedReportProject
}

interface Viewport {
  width: number
  height: number
}

const projectPath = process.env.REPORT_PROJECT_PATH
const keepOutputs = process.env.KEEP_HTML_VISUAL_OUTPUT === '1'
const outputDir = process.env.REPORT_VISUAL_OUTPUT_DIR
  ? resolve(process.env.REPORT_VISUAL_OUTPUT_DIR)
  : mkdtempSync(join(tmpdir(), 'por-html-visual-'))
const viewports: Viewport[] = [
  { width: 320, height: 760 },
  { width: 375, height: 812 },
  { width: 414, height: 896 },
  { width: 768, height: 1024 },
  { width: 1440, height: 1000 },
  { width: 2560, height: 1080 }
]
let activeWindow: BrowserWindow | null = null

const SAMPLE_REPORT = `# 示例产品 产品经营报告
生成日期：2026-07-27

<!-- Product visual brief
role: 家庭日常快速配餐
audience: 需要快速理解经营结论的小白用户
scene: 工作日晚餐
value-signal: practicality
trust-model: visible-use
design-direction: household-field-guide
evidence-confidence: confirmed
-->

## 0. 结论先行
优先服务家庭做饭决策者，先用真实使用场景证明方便，再补充产品信任。

| 优先级 | 核心人群 | 关键判断 |
|---|---|---|
| P1 | 31-45岁家庭做饭人群 | 先讲快手晚餐 |
| P2 | 家庭囤货人群 | 再讲多场景使用 |

## 1. 数据来源与使用范围
| 数据类型 | 来源 | 本次用途 |
|---|---|---|
| 成交人群 | 示例平台 | 判断核心人群 |

## 2. 产品基础信息
| 模块 | 当前判断 |
|---|---|
| 产品 | 示例产品 |
| 场景 | 家庭晚餐 |

## 3. 一方数据核心判断
### 3.1 示例平台成交人群
| 维度 | 关键数据 | 经营含义 |
|---|---|---|
| 性别 | 女性占比 68.4% | 内容优先服务家庭做饭决策者 |
| 婚育 | 已育占比 71.2% | 强调家庭场景 |

## 4. 竞品与素材打法判断
| 类型 | 原始 3 秒开头 | 可复用方向 |
|---|---|---|
| 场景型 | 下班吃什么 | 快手晚餐 |

## 5. 产品全量卖点拆解
| 卖点维度 | 我方产品卖点 | 用户能感知的好处 |
|---|---|---|
| 原料 | 自然发酵酸菜，配料简单 | 家庭做菜能直接感知酸菜发酵风味 |
| 使用 | 酸菜分袋，快速做菜 | 家庭晚餐做菜更快速 |
| 信任 | 配料清晰，发酵过程可见 | 家庭选择酸菜时更容易核对配料 |
| 场景 | 家庭日常酸菜做法 | 快速完成一顿家庭饭菜 |

## 6. 卖点用户视角排序
| 排序 | 用户视角卖点 | 对应产品事实 | 打动的人群/场景 | 作用 |
|---|---|---|---|---|
| 1 | 做饭更省事 | 打开即可使用 | 工作日晚餐 | 拉动需求 |

## 7. 核心成交人群画像与卖点场景匹配
| 优先级 | 成交人群 | 数据依据/特征 | 核心卖点 | 核心场景 | 内容语言 |
|---|---|---|---|---|---|
| P1 | 家庭做饭人群 | 女性占比 68.4% | 少准备步骤 | 工作日晚餐 | 直接易懂 |

## 8. 视频号内容主线设计
| 内容主线 | 对应人群 | 选题方向 | 建议占比 |
|---|---|---|---|
| 快手晚餐 | 家庭做饭人群 | 下班吃什么 | 60% |
| 多场景使用 | 家庭囤货人群 | 一袋多做法 | 40% |

## 9. 内容执行方向
| 脚本编号 | 选题 | 3 秒开头 | 视频分类 | 视角 |
|---|---|---|---|---|
| S01 | 快手晚餐 | 下班吃什么 | 3.1 | 用户 |
| S02 | 使用证明 | 打开直接用 | 3.2 | 商家 |

## 10. 经营建议
1. 短期优先放大快手晚餐内容线。
2. 持续按平台拆分人群表达。
3. 检测报告待补充后再放大信任内容。

## 11. 本次报告的限制
- 示例数据仅用于布局和离线测试。
- 正式结论必须以用户导入资料为准。
`

function ensureWithResolvers(): void {
  const promiseConstructor = Promise as unknown as { withResolvers?: () => unknown }
  if (typeof promiseConstructor.withResolvers === 'function') return
  promiseConstructor.withResolvers = function <T>() {
    let resolvePromise!: (value: T | PromiseLike<T>) => void
    let rejectPromise!: (reason?: unknown) => void
    const promise = new Promise<T>((resolve, reject) => {
      resolvePromise = resolve
      rejectPromise = reject
    })
    return { promise, resolve: resolvePromise, reject: rejectPromise }
  }
}

function markerText(value: string): string {
  return value
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/<[^>]*>/g, '')
    .replace(/[*_`]/g, '')
    .replace(/\s+/g, '')
    .trim()
}

async function readPdfAudit(pdfPath: string): Promise<{
  text: string
  pageSizes: Array<{ width: number; height: number }>
  pageTexts: string[]
}> {
  ensureWithResolvers()
  const [pdfjs, pdfWorker] = await Promise.all([
    import('pdfjs-dist/legacy/build/pdf.mjs'),
    import('pdfjs-dist/legacy/build/pdf.worker.mjs')
  ])
  ;(
    globalThis as typeof globalThis & {
      pdfjsWorker?: typeof pdfWorker
    }
  ).pdfjsWorker ??= pdfWorker
  const document = await pdfjs.getDocument({
    data: new Uint8Array(readFileSync(pdfPath)),
    useSystemFonts: true,
    isEvalSupported: false
  }).promise
  const pages: string[] = []
  const pageSizes: Array<{ width: number; height: number }> = []
  try {
    for (let pageNumber = 1; pageNumber <= document.numPages; pageNumber++) {
      const page = await document.getPage(pageNumber)
      const viewport = page.getViewport({ scale: 1 })
      pageSizes.push({ width: viewport.width, height: viewport.height })
      const content = await page.getTextContent()
      pages.push(
        content.items
          .map((item) => ('str' in item ? (item as { str: string }).str : ''))
          .join('')
      )
    }
  } finally {
    await document.cleanup()
    await document.destroy()
  }
  return {
    text: markerText(pages.join('')),
    pageSizes,
    pageTexts: pages.map(markerText)
  }
}

async function runAudit(): Promise<void> {
  let markdown = SAMPLE_REPORT
  let projectName = '内置匿名样本'
  if (projectPath) {
    const saved = JSON.parse(readFileSync(projectPath, 'utf8')) as SavedReportProject
    const project = saved.project || saved
    assert.equal(typeof project.reportMarkdown, 'string', '项目中没有可导出的报告。')
    assert.ok(project.reportMarkdown.trim(), '项目中的报告为空。')
    markdown = project.reportMarkdown
    projectName = basename(projectPath)
  }

  mkdirSync(outputDir, { recursive: true })
  const model = parseHtmlReportModel(markdown)
  const presentation = buildHtmlReportPresentation(model)
  const printMarkers = presentation.sections
    .flatMap((sectionPlan) =>
      sectionPlan.tables
        .filter((tablePlan) => tablePlan.mode === 'collapsed')
        .flatMap((tablePlan) => {
          const table = model.sections
            .find((section) => section.number === sectionPlan.sectionNumber)
            ?.tables[tablePlan.tableIndex]
          if (!table || table.rows.length === 0) return []
          return [table.rows[0], table.rows[table.rows.length - 1]]
            .map((row) => row.map(markerText).find((cell) => cell.length >= 2) || '')
            .filter(Boolean)
        })
    )
    .filter((value, index, values) => values.indexOf(value) === index)
  const html = await markdownToHtmlDocument(markdown)
  const htmlPath = join(outputDir, 'report-preview.html')
  writeFileSync(htmlPath, html, 'utf8')
  if (process.env.HTML_VISUAL_TEST_FORCE_FAILURE === '1') {
    throw new Error('HTML visual cleanup failure-path probe')
  }

  const errors: string[] = []
  const externalRequests: string[] = []
  const window = (activeWindow = new BrowserWindow({
    show: false,
    width: 1440,
    height: 1000,
    backgroundColor: '#f4f6f5',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      backgroundThrottling: false
    }
  }))
  window.webContents.on('console-message', (_event, level, message) => {
    if (level >= 2) errors.push(message)
  })
  window.webContents.session.webRequest.onBeforeRequest({ urls: ['http://*/*', 'https://*/*'] }, (details) => {
    externalRequests.push(details.url)
  })
  await window.loadFile(htmlPath)

  const expectedDonuts = presentation.sections.reduce(
    (sum, sectionPlan) =>
      sum +
      sectionPlan.executionDistributions.length +
      (sectionPlan.contentMix?.mode === 'stacked' ? 1 : 0),
    0
  )
  const expectedWordClouds = presentation.sections.filter(
    (sectionPlan) => sectionPlan.keywordCloud
  ).length
  const visualAudit = (await window.webContents.executeJavaScript(
    `(() => ({
      donuts: document.querySelectorAll('.donut-chart').length,
      visibleDonuts: Array.from(document.querySelectorAll('.donut-chart')).filter((element) => {
        const rect = element.getBoundingClientRect()
        return rect.width >= 120 && rect.height >= 120 && getComputedStyle(element).backgroundImage !== 'none'
      }).length,
      wordClouds: document.querySelectorAll('.word-cloud').length,
      wordItems: Array.from(document.querySelectorAll('.word-cloud__item')).filter((element) =>
        Number(element.getAttribute('data-count')) >= 2
      ).length
    }))()`
  )) as { donuts: number; visibleDonuts: number; wordClouds: number; wordItems: number }
  assert.equal(visualAudit.donuts, expectedDonuts, '环图数量与展示模型不一致。')
  assert.equal(visualAudit.visibleDonuts, expectedDonuts, '环图未正确显示或尺寸过小。')
  assert.equal(visualAudit.wordClouds, expectedWordClouds, '词云数量与展示模型不一致。')
  if (expectedWordClouds > 0) {
    assert.ok(visualAudit.wordItems >= 6, '词云未显示足够的可核对高频词。')
  }

  const keyboardAudit = (await window.webContents.executeJavaScript(
    `(() => {
      const focusable = Array.from(document.querySelectorAll('a[href], summary, [tabindex]'))
        .filter((element) => {
          const style = getComputedStyle(element)
          return style.display !== 'none' && style.visibility !== 'hidden'
        })
      const summary = document.querySelector('.evidence-disclosure summary')
      if (!(summary instanceof HTMLElement)) {
        return { firstClass: focusable[0]?.className || '', summaryFound: false, summaryFocused: false }
      }
      summary.focus()
      return {
        firstClass: focusable[0]?.className || '',
        summaryFound: true,
        summaryFocused: document.activeElement === summary,
        initiallyOpen: summary.parentElement?.hasAttribute('open') || false
      }
    })()`
  )) as {
    firstClass: string
    summaryFound: boolean
    summaryFocused: boolean
    initiallyOpen?: boolean
  }
  assert.equal(keyboardAudit.firstClass, 'skip-link', '键盘焦点顺序应先到“跳到报告正文”。')
  assert.equal(keyboardAudit.summaryFound, true, '长表必须提供可聚焦的展开入口。')
  assert.equal(keyboardAudit.summaryFocused, true, '长表展开入口无法通过键盘获得焦点。')
  assert.equal(keyboardAudit.initiallyOpen, false, '长表在屏幕端应默认折叠。')
  const disclosureOpened = await window.webContents.executeJavaScript(
    `(() => {
      const summary = document.querySelector('.evidence-disclosure summary')
      if (!(summary instanceof HTMLElement)) return false
      summary.click()
      return summary.parentElement?.hasAttribute('open') || false
    })()`
  )
  assert.equal(disclosureOpened, true, '完整数据入口无法展开。')
  await window.webContents.executeJavaScript(
    `(() => {
      const summary = document.querySelector('.evidence-disclosure summary')
      if (summary instanceof HTMLElement && summary.parentElement?.hasAttribute('open')) summary.click()
    })()`
  )

  let reducedMotionBehavior = ''
  try {
    window.webContents.debugger.attach('1.3')
    await window.webContents.debugger.sendCommand('Emulation.setEmulatedMedia', {
      media: 'screen',
      features: [{ name: 'prefers-reduced-motion', value: 'reduce' }]
    })
    reducedMotionBehavior = await window.webContents.executeJavaScript(
      `getComputedStyle(document.documentElement).scrollBehavior`
    )
    assert.equal(reducedMotionBehavior, 'auto', '减少动效设置未关闭平滑滚动。')
  } finally {
    if (window.webContents.debugger.isAttached()) window.webContents.debugger.detach()
  }

  const captures: string[] = []
  const viewportLayout: Array<Viewport & { innerWidth: number; scrollWidth: number }> = []
  for (const viewport of viewports) {
    window.setContentSize(viewport.width, viewport.height)
    let layout = { innerWidth: -1, scrollWidth: -1 }
    for (let attempt = 0; attempt < 20; attempt++) {
      await new Promise((resolveWait) => setTimeout(resolveWait, 50))
      layout = (await window.webContents.executeJavaScript(
        `({ innerWidth: window.innerWidth, scrollWidth: document.documentElement.scrollWidth })`
      )) as { innerWidth: number; scrollWidth: number }
      if (Math.abs(layout.innerWidth - viewport.width) <= 1) break
    }
    viewportLayout.push({ ...viewport, ...layout })
    assert.ok(
      Math.abs(layout.innerWidth - viewport.width) <= 1,
      `视口设置失败：目标 ${viewport.width}px，实际 ${layout.innerWidth}px。`
    )
    assert.ok(
      layout.scrollWidth <= layout.innerWidth + 1,
      `${viewport.width}px 视口出现横向滚动：内容 ${layout.scrollWidth}px，视口 ${layout.innerWidth}px。`
    )
    await window.webContents.executeJavaScript(`window.scrollTo({ top: 0, behavior: 'auto' })`)
    const image = await window.webContents.capturePage()
    const file = join(outputDir, `report-${viewport.width}x${viewport.height}.png`)
    writeFileSync(file, image.toPNG())
    captures.push(file)
  }
  const pdfPath = join(outputDir, 'report-print.pdf')
  writeFileSync(
    pdfPath,
    await window.webContents.printToPDF({
      pageSize: 'A4',
      printBackground: true,
      preferCSSPageSize: true
    })
  )
  const pdfAudit = await readPdfAudit(pdfPath)
  for (const marker of printMarkers) {
    assert.ok(
      pdfAudit.text.includes(marker),
      `打印 PDF 丢失折叠表数据：未找到“${marker}”。`
    )
  }
  assert.ok(
    pdfAudit.pageSizes.some((page) => page.height > page.width),
    '打印 PDF 缺少纵向页面。'
  )
  if (/<div class="table-wrap[^"]*wide-table/u.test(html)) {
    assert.ok(
      pdfAudit.pageSizes.some((page) => page.width > page.height),
      '宽表未进入横向打印页面。'
    )
  }
  const blankPrintPages = pdfAudit.pageTexts
    .map((pageText, index) => ({ page: index + 1, chars: pageText.length }))
    .filter((page) => page.chars < 2)
  assert.deepEqual(blankPrintPages, [], `打印 PDF 出现空白页：${blankPrintPages.map((page) => page.page).join('、')}`)
  window.setContentSize(1440, 1000)
  const sectionNumbers = model.sections.map((section) => section.number)
  const sectionLayout = (await window.webContents.executeJavaScript(
    `Array.from(document.querySelectorAll('[data-section]')).map((element) => ({
      section: element.getAttribute('data-section'),
      top: Math.round(element.getBoundingClientRect().top + window.scrollY),
      height: Math.round(element.getBoundingClientRect().height)
    }))`
  )) as Array<{ section: string; top: number; height: number }>
  const sectionPositions: Record<string, number> = {}
  for (const sectionNumber of sectionNumbers) {
    sectionPositions[sectionNumber] = await window.webContents.executeJavaScript(
      `(() => {
        const target = document.querySelector('[data-section="${sectionNumber}"]')
        if (!target) return -1
        const top = target.getBoundingClientRect().top + window.scrollY
        const previous = document.documentElement.style.scrollBehavior
        document.documentElement.style.scrollBehavior = 'auto'
        window.scrollTo({ top, behavior: 'auto' })
        document.documentElement.style.scrollBehavior = previous
        return window.scrollY
      })()`
    )
    await new Promise((resolveWait) => setTimeout(resolveWait, 80))
    const image = await window.webContents.capturePage()
    const file = join(outputDir, `report-1440-section-${sectionNumber}.png`)
    writeFileSync(file, image.toPNG())
    captures.push(file)
  }
  window.setContentSize(320, 760)
  await new Promise((resolveWait) => setTimeout(resolveWait, 120))
  const mobileSectionPositions: Record<string, number> = {}
  for (const sectionNumber of sectionNumbers) {
    mobileSectionPositions[sectionNumber] = await window.webContents.executeJavaScript(
      `(() => {
        const target = document.querySelector('[data-section="${sectionNumber}"]')
        if (!target) return -1
        const top = target.getBoundingClientRect().top + window.scrollY
        const previous = document.documentElement.style.scrollBehavior
        document.documentElement.style.scrollBehavior = 'auto'
        window.scrollTo({ top, behavior: 'auto' })
        document.documentElement.style.scrollBehavior = previous
        return window.scrollY
      })()`
    )
    await new Promise((resolveWait) => setTimeout(resolveWait, 80))
    const mobileLayout = (await window.webContents.executeJavaScript(
      `({ innerWidth: window.innerWidth, scrollWidth: document.documentElement.scrollWidth })`
    )) as { innerWidth: number; scrollWidth: number }
    assert.ok(
      mobileLayout.scrollWidth <= mobileLayout.innerWidth + 1,
      `320px 章节 ${sectionNumber} 出现横向滚动：内容 ${mobileLayout.scrollWidth}px，视口 ${mobileLayout.innerWidth}px。`
    )
    const image = await window.webContents.capturePage()
    const file = join(outputDir, `report-320-section-${sectionNumber}.png`)
    writeFileSync(file, image.toPNG())
    captures.push(file)
  }
  const materialCloudPath = join(outputDir, 'material-cloud-preview.html')
  writeFileSync(materialCloudPath, await markdownToHtmlDocument(
    '# 素材卖点视觉测试\n\n## M4 卖点提炼与排序\n\n来源：测试素材',
    { version: 1, fingerprint: 'visual', scopeLabel: '产品甲', totalMaterials: 4,
      effectiveMaterials: 3, normalizedCount: 2, mappings: [], items: [
        { keyword: '安装方便', materialCount: 3, coverageRate: 0.75, top1Count: 2, top2Count: 1,
          top3Count: 0, unrankedCount: 0, rankScore: 8, evidence: [{
            sourceId: 'source-1', sourceName: '内容分析表.xlsx', sheetName: 'Sheet1',
            rowEvidenceId: 'POR-R-AAAA0000-000001', materialKey: 'material-1', topRank: 1,
            rawDescription: 'Top1：安装方便', evidenceSnippet: '安装方便', candidate: '安装方便', keyword: '安装方便'
          }] },
        { keyword: '含安装服务', materialCount: 1, coverageRate: 0.25, top1Count: 0, top2Count: 0,
          top3Count: 0, unrankedCount: 1, rankScore: 0, evidence: [] }
      ] }
  ), 'utf8')
  await window.loadFile(materialCloudPath)
  for (const width of [320, 375, 768, 1440]) {
    window.setContentSize(width, 900)
    const audit = await window.webContents.executeJavaScript(`(() => {
      const words = Array.from(document.querySelectorAll('.material-insight-words .word-cloud__item'))
      return { innerWidth: window.innerWidth, scrollWidth: document.documentElement.scrollWidth,
        sizes: words.map((word) => getComputedStyle(word).fontSize),
        titles: words.map((word) => word.getAttribute('title')),
        summary: document.querySelector('.material-insight-summary')?.textContent || '' }
    })()`)
    assert.ok(audit.scrollWidth <= audit.innerWidth + 1, `${width}px 素材卖点词云出现横向滚动`)
    assert.equal(audit.sizes.length, 2)
    assert.ok(Number.parseFloat(audit.sizes[0]) > Number.parseFloat(audit.sizes[1]), '词云字号必须随素材数增大')
    assert.match(audit.titles[0], /Top1 2 \/ Top2 1/u)
    assert.match(audit.summary, /分析素材\s*4/u)
  }
  const materialPrintPath = join(outputDir, 'material-cloud-print.pdf')
  writeFileSync(materialPrintPath, await window.webContents.printToPDF({ pageSize: 'A4', printBackground: true }))
  const materialPrint = await readPdfAudit(materialPrintPath)
  assert.match(materialPrint.text, /素材高频卖点\s*Top20/u)
  assert.match(materialPrint.text, /内容分析表.xlsx/u)
  const scenePath = join(outputDir, 'need-scene-preview.html')
  const sceneId = 'SC-1234abcd-0001'
  writeFileSync(scenePath, await markdownToHtmlDocument(
    `# 场景视觉测试\n\n## M6 人群×卖点×场景匹配\nTOP1\n核心人群：家庭用户\n核心卖点：安装方便\n真实场景：下班回家安装\n场景状态：已验证\n场景依据：需求场景｜${sceneId}`,
    undefined, 'missing', [{ id: sceneId, text: '下班回家安装', attribution: '自有数据', materialCount: 1,
      sources: [{ sourceName: '需求场景表.xlsx', sheetName: 'Sheet1', rowEvidenceId: 'POR-R-BBBB0000-000001', materialKey: 'm1' }] }]
  ), 'utf8')
  await window.loadFile(scenePath)
  const scenePrintPath = join(outputDir, 'need-scene-print.pdf')
  writeFileSync(scenePrintPath, await window.webContents.printToPDF({ pageSize: 'A4', printBackground: true }))
  const scenePrint = await readPdfAudit(scenePrintPath)
  assert.match(scenePrint.text, /需求场景表.xlsx/u)
  const merchantAudit: Array<{ name: string; style: string; variant: string; words: number }> = []
  for (const [name, product, brand, expected] of [
    ['food', '发酵酸菜', '示例食品', 'household-field-guide'],
    ['beauty', '补水面霜', '示例美妆', 'restrained-catalogue'],
    ['home', '记忆棉枕头', '示例家居', 'material-editorial'],
    ['technology', '无线耳机', '示例数码', 'technical-workbench']
  ]) {
    const previewPath = join(outputDir, `merchant-${name}.html`)
    writeFileSync(previewPath, await markdownToHtmlDocument(merchantDesignFixture(product, brand), cloudDesignFixture(), 'ready'))
    await window.loadFile(previewPath)
    for (const width of [320, 375, 414, 768, 1440]) {
      window.setContentSize(width, 1000)
      await new Promise(resolveWait => setTimeout(resolveWait, 60))
      const measured = await window.webContents.executeJavaScript(`(() => {
        const visible = e => e.getBoundingClientRect().width > 0 && e.getBoundingClientRect().height > 0
        return { width:innerWidth,scroll:document.documentElement.scrollWidth,
          style:document.body.dataset.reportStyle,variant:document.body.dataset.brandVariant,
          words:document.querySelectorAll('.cloud-control').length,
          panels:[...document.querySelectorAll('.cloud-evidence-panel')].filter(visible).length,
          clippedWords:[...document.querySelectorAll('.word-cloud__item')].filter(e=>e.getBoundingClientRect().right>innerWidth).length,
          navClipped:[...document.querySelectorAll('.toc a')].filter(e=>e.scrollWidth>e.clientWidth+1).length }
      })()`)
      assert.equal(measured.style, expected)
      assert.equal(measured.words, 20)
      assert.equal(measured.panels, 1, 'Only the selected keyword evidence should be visible')
      assert.ok(measured.scroll <= measured.width + 1, `${name} ${width}px report overflow`)
      assert.equal(measured.clippedWords, 0)
      assert.equal(measured.navClipped, 0)
      if (width === 1440) {
        merchantAudit.push({ name, style: measured.style, variant: measured.variant, words: measured.words })
        const contrastFailures = await window.webContents.executeJavaScript(`(() => {
          const ctx=document.createElement('canvas').getContext('2d',{willReadFrequently:true});ctx.canvas.width=ctx.canvas.height=1
          const rgb=color=>{ctx.clearRect(0,0,1,1);ctx.fillStyle=color;ctx.fillRect(0,0,1,1);return [...ctx.getImageData(0,0,1,1).data]}
          const luminance=rgb=>rgb.slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((v,c,i)=>v+c*[.2126,.7152,.0722][i],0)
          return [...document.querySelectorAll('h1,.hero-thesis,.hero-report-label,.visual-note,.toc a,.cloud-axis-note,.cloud-ranking,.cloud-evidence-panel > p')].filter(el=>el.getBoundingClientRect().height>0).flatMap(el=>{
            const style=getComputedStyle(el);let bg=[255,255,255,255];let parent=el
            while(parent){const color=rgb(getComputedStyle(parent).backgroundColor);if(color[3]===255){bg=color;break}parent=parent.parentElement}
            const text=luminance(rgb(style.color)),background=luminance(bg);const ratio=(Math.max(text,background)+.05)/(Math.min(text,background)+.05)
            const threshold=parseFloat(style.fontSize)>=24||(parseInt(style.fontWeight)>=700&&parseFloat(style.fontSize)>=18)?3:4.5
            return ratio+0.01<threshold?[{selector:el.className||el.tagName,ratio,threshold}]:[]
          })
        })()`)
        assert.deepEqual(contrastFailures, [], `${name}: text contrast below WCAG threshold`)
      }
      await window.webContents.executeJavaScript('window.scrollTo({top:0,behavior:"instant"})')
      const cover = join(outputDir, `merchant-${name}-${width}.png`)
      writeFileSync(cover, (await window.webContents.capturePage()).toPNG())
      captures.push(cover)
    }
    await window.webContents.executeJavaScript('document.querySelector(".material-insight-cloud").scrollIntoView({block:"start",behavior:"instant"})')
    const beforeY = await window.webContents.executeJavaScript('window.scrollY')
    await window.webContents.executeJavaScript('document.getElementById("cloud-term-7").click()')
    const selected = await window.webContents.executeJavaScript(`({ visible:getComputedStyle(document.getElementById('cloud-evidence-7')).display !== 'none', oldHidden:getComputedStyle(document.getElementById('cloud-evidence-0')).display === 'none', y:window.scrollY })`)
    assert.equal(selected.visible, true)
    assert.equal(selected.oldHidden, true)
    assert.ok(Math.abs(selected.y - beforeY) < 2, 'Keyword selection must not jump to the page top')
    await new Promise(resolveWait => setTimeout(resolveWait, 100))
    const cloud = join(outputDir, `merchant-${name}-cloud.png`)
    writeFileSync(cloud, (await window.webContents.capturePage()).toPNG())
    captures.push(cloud)
    await window.webContents.executeJavaScript('document.getElementById("cloud-term-7").focus()')
    window.webContents.sendInputEvent({ type: 'keyDown', keyCode: 'Right' })
    window.webContents.sendInputEvent({ type: 'keyUp', keyCode: 'Right' })
    await new Promise(resolveWait => setTimeout(resolveWait, 50))
    assert.equal(await window.webContents.executeJavaScript('document.getElementById("cloud-term-8").checked'), true, 'Cloud keyboard navigation failed')
  }
  window.close()
  activeWindow = null

  assert.deepEqual(errors, [], `HTML 控制台出现错误：${errors.join('；')}`)
  assert.deepEqual(externalRequests, [], `HTML 发起了外部请求：${externalRequests.join('；')}`)
  const result = JSON.stringify(
    {
      project: projectName,
      outputsRetained: keepOutputs,
      outputDir: keepOutputs ? outputDir : '已自动清理',
      htmlPath: keepOutputs ? htmlPath : null,
      captures: keepOutputs ? captures : [],
      pdfPath: keepOutputs ? pdfPath : null,
      viewportLayout,
      sectionLayout,
      sectionPositions,
      mobileSectionPositions,
      keyboardAudit: {
        firstClass: keyboardAudit.firstClass,
        summaryFocused: keyboardAudit.summaryFocused,
        disclosureOpened
      },
      reducedMotionBehavior,
      merchantAudit,
      printPages: pdfAudit.pageSizes,
      externalRequests: externalRequests.length,
      consoleErrors: errors.length
    },
    null,
    2
  )
  if (keepOutputs) writeFileSync(join(outputDir, 'visual-audit.json'), result)
  process.stdout.write(`${result}\n`)
}

async function run(): Promise<void> {
  try {
    await runAudit()
  } finally {
    if (activeWindow && !activeWindow.isDestroyed()) activeWindow.close()
    activeWindow = null
    if (!keepOutputs && existsSync(outputDir)) {
      rmSync(outputDir, { recursive: true, force: true })
    }
  }
}

app.disableHardwareAcceleration()
app
  .whenReady()
  .then(run)
  .then(() => app.quit())
  .catch((error) => {
    console.error(error)
    app.exit(1)
  })
