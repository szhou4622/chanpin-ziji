import { useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { buildEvidenceSourceNameMap, reportMarkdownForDisplay, splitReportAtSellingPoints } from '../../../shared/reportDisplay'
import { useStore } from '../store'
import { validateReport, validateReportStructure } from '../validate'
import { materialInsightFingerprint, readMaterialInsightRows, selectMaterialInsightScope } from '../materialInsights'
import { materialInsightTaskPrefix, readMaterialInsightResult } from '../materialInsightWorkflow'

export default function ReportPreview(): JSX.Element {
  const reportMarkdown = useStore((s) => s.reportMarkdown)
  const cleanDetails = useStore((s) => s.cleanDetails)
  const sources = useStore((s) => s.sources)
  const selectedMaterialProducts = useStore((s) => s.selectedMaterialProducts)
  const taskJournal = useStore((s) => s.taskJournal)
  const analysisSessionId = useStore((s) => s.analysisSessionId)
  const retryMaterialInsight = useStore((s) => s.retryMaterialInsight)
  const reportStale = useStore((s) => s.reportStale)
  const artifacts = useStore((s) => s.artifacts)
  const phase = useStore((s) => s.phase)
  const exportStatus = useStore((s) => s.exportStatus)
  const lastExportPath = useStore((s) => s.lastExportPath)
  const openingExport = useStore((s) => s.openingExport)
  const exportReport = useStore((s) => s.exportReport)
  const openLastExport = useStore((s) => s.openLastExport)
  const showLastExportInFolder = useStore((s) => s.showLastExportInFolder)

  const reportGenerating = phase === 'cleaning' || phase === 'analyzing'
  const insightScope = useMemo(() => selectMaterialInsightScope(
    readMaterialInsightRows(sources), selectedMaterialProducts
  ), [sources, selectedMaterialProducts])
  const insightFingerprint = useMemo(() => materialInsightFingerprint(
    insightScope.rows, insightScope.selectedProducts
  ), [insightScope])
  const insightTaskId = `${materialInsightTaskPrefix(analysisSessionId, insightFingerprint)}:final`
  const materialInsight = useMemo(() => !reportStale && !insightScope.needsSelection
    ? readMaterialInsightResult(taskJournal, analysisSessionId, insightFingerprint) : null,
  [taskJournal, analysisSessionId, insightFingerprint, insightScope.needsSelection, reportStale])
  const cloudCounts = materialInsight?.items.map((item) => item.materialCount) || []
  const cloudMin = cloudCounts.length ? Math.min(...cloudCounts) : 0
  const cloudMax = cloudCounts.length ? Math.max(...cloudCounts) : 0
  const materialInsightTaskStatus = taskJournal[insightTaskId]?.status
  const evidenceSourceNames = useMemo(
    () => buildEvidenceSourceNameMap(cleanDetails),
    [cleanDetails]
  )
  const displayReportMarkdown = useMemo(
    () => reportMarkdownForDisplay(reportMarkdown, evidenceSourceNames),
    [reportMarkdown, evidenceSourceNames]
  )
  const exporting = exportStatus === '导出中…'
  const warnings = useMemo(
    () => (reportGenerating ? [] : validateReport(reportMarkdown)),
    [reportGenerating, reportMarkdown]
  )
  const canExport =
    Boolean(reportMarkdown) &&
    !reportGenerating &&
    !exporting &&
    artifacts[9] === reportMarkdown &&
    (phase === 'done' || reportStale) &&
    validateReportStructure(reportMarkdown).length === 0
  const headings = useMemo(
    () =>
      displayReportMarkdown
        .split('\n')
        .map((line) => line.match(/^(#{1,3})\s+(.+)$/))
        .filter((m): m is RegExpMatchArray => Boolean(m))
        .slice(0, 18)
        .map((m) => ({ level: m[1].length, text: m[2].replace(/\*\*/g, '') })),
    [displayReportMarkdown]
  )
  const m4Sections = splitReportAtSellingPoints(displayReportMarkdown)
  const materialCloud = m4Sections === null ? null : (
    <section className="report-material-insight-preview" aria-label="素材高频卖点预览">
      <h3>素材高频卖点 Top20</h3>
      {materialInsight ? <>
        <p>分析范围：{materialInsight.scopeLabel}；分析素材 {materialInsight.totalMaterials} 份，
          有效卖点素材 {materialInsight.effectiveMaterials} 份，归一后 {materialInsight.normalizedCount} 个，展示 {materialInsight.items.length} 个。</p>
        {materialInsight.items.length ? <div className="report-material-insight-words">
          {materialInsight.items.map((item) => {
            const size = cloudMin === cloudMax ? 20 : Math.round(14 + (item.materialCount - cloudMin) / (cloudMax - cloudMin) * 14)
            return <span key={item.keyword} style={{ fontSize: size }} title={`${item.keyword}：${item.materialCount}份素材，覆盖率 ${(item.coverageRate * 100).toFixed(1)}%`}>
              {item.keyword} ×{item.materialCount}</span>
          })}
        </div> : <p>未从卖点排序字段中识别到可统计卖点。</p>}
      </> : <>
        <p>{materialInsightTaskStatus === 'failed' ? '卖点提取未完成，词云待重试。' :
          materialInsightTaskStatus === 'interrupted' ? '正在重试卖点词云…' : '本报告尚未生成新版素材卖点统计。'}</p>
        {!reportGenerating && !reportStale && phase === 'done' && materialInsightTaskStatus !== 'interrupted' && (
          <button className="btn xs" type="button" onClick={() => void retryMaterialInsight()}>
            重试素材卖点词云（会按实际模型用量扣积分）
          </button>
        )}
      </>}
    </section>
  )

  return (
    <div className={`pane report-pane ${phase === 'checkpoint2' || phase === 'done' ? 'report-ready' : ''}`} style={{ borderRight: 'none' }}>
      <div className="pane-title report-title-bar">
        <span>{reportGenerating && reportMarkdown ? '报告生成中…' : reportMarkdown ? '报告预览' : '报告大纲'}</span>
        {reportMarkdown && (
          <span className="export-bar">
            <button className="btn xs primary" disabled={!canExport} onClick={() => void exportReport('html')}>
              导出 HTML
            </button>
            <button className="btn xs" disabled={!canExport} onClick={() => void exportReport('md')}>
              导出 MD
            </button>
            <button className="btn xs" disabled={!canExport} onClick={() => void exportReport('docx')}>
              导出 Word
            </button>
          </span>
        )}
      </div>
      <div className="pane-body">
        {reportMarkdown ? (
          <div className="report-content">
            <aside className="report-outline-nav">
              <div className="outline-title">目录</div>
              {headings.map((h, i) => (
                <div key={`${h.text}-${i}`} className={`outline-link level-${h.level}`}>
                  {h.text}
                </div>
              ))}
            </aside>
            <main className="report-canvas">
              {reportStale && (
                <div className="warnings">
                  <div className="warnings-title">资料已变化</div>
                  <div>当前保留的是上一份完整报告，可先导出备份；重新生成成功后会自动替换。</div>
                </div>
              )}
              {phase === 'checkpoint2' ? (
                <div className="warnings">
                  <div className="warnings-title">这是待确认的初稿</div>
                  <div>请先检查内容，再点击左侧“确认定稿”；定稿后才能导出最终报告。</div>
                </div>
              ) : reportGenerating ? (
                <div className="structure-ok">报告正在生成，完成后才能导出。</div>
              ) : warnings.length > 0 ? (
                <div className="warnings">
                  <div className="warnings-title">成稿检查（{warnings.length}）</div>
                  <ul>
                    {warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </div>
              ) : (
                <div className="structure-ok">成稿结构符合目标报告模板</div>
              )}
              {exportStatus && (
                <div className="export-status">
                  <span>{exportStatus}</span>
                  {lastExportPath && (
                    <div className="export-result-actions">
                      <button
                        className="btn xs primary"
                        disabled={openingExport}
                        onClick={() => void openLastExport()}
                      >
                        {openingExport ? '正在打开…' : '打开刚导出的文件'}
                      </button>
                      <button
                        className="btn xs"
                        disabled={openingExport}
                        onClick={() => void showLastExportInFolder()}
                      >
                        打开所在文件夹
                      </button>
                    </div>
                  )}
                </div>
              )}
              <div className="markdown-body">
                {m4Sections ? <>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{m4Sections[0]}</ReactMarkdown>
                  {materialCloud}
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{m4Sections[1]}</ReactMarkdown>
                </> : <ReactMarkdown remarkPlugins={[remarkGfm]}>{displayReportMarkdown}</ReactMarkdown>}
              </div>
            </main>
          </div>
        ) : (
          <div className="report-body">
            <div className="report-placeholder-title">报告生成后会进入文档画布</div>
            <div className="report-placeholder-copy">
              系统会把已确认的资料清洗、卖点、人群和内容策略整合成一份可导出的经营报告。
            </div>
            <div className="report-skeleton-list">
              {['结论摘要', '数据来源与使用范围', '产品基础信息', '一方数据判断', '竞品/素材分析', '人群画像与内容主线', '执行选题表'].map((item) => (
                <span key={item}>{item}</span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
