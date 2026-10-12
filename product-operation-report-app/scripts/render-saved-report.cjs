// Render an existing completed project offline. No model, activation or billing calls.
const fs = require('node:fs')
const path = require('node:path')
const crypto = require('node:crypto')
const Module = require('node:module')
const { buildSync } = require('esbuild')

const args = process.argv.slice(2)
if (args.length !== 2 || args.includes('--help')) {
  console.log('Usage: node scripts/render-saved-report.cjs PROJECT_JSON OUTPUT_HTML')
  process.exit(args.includes('--help') ? 0 : 1)
}
const projectFile = path.resolve(args[0])
const destination = path.resolve(args[1])
if (fs.existsSync(destination)) throw Error('Refuse to overwrite an existing report')
const raw = fs.readFileSync(projectFile)
const hash = value => crypto.createHash('sha256').update(value).digest('hex')
const blobs = new Set()
function hydrate(value) {
  if (!value || typeof value !== 'object') return value
  if (value.$blob) {
    if (!/^[a-f0-9]{64}$/.test(value.$blob)) throw Error('Invalid project blob name')
    const bytes = fs.readFileSync(path.join(path.dirname(projectFile), 'project-data', 'blobs', value.$blob + '.txt'))
    if (bytes.length !== value.bytes || hash(bytes) !== value.$blob) throw Error('Project blob integrity check failed')
    blobs.add(value.$blob)
    return bytes.toString('utf8')
  }
  if (Array.isArray(value)) return value.map(hydrate)
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, hydrate(item)]))
}
const project = hydrate(JSON.parse(raw).project)
if (project?.phase !== 'done' || !project.reportMarkdown?.trim()) throw Error('A completed project is required')
const root = path.resolve(__dirname, '..')
const compiled = buildSync({
  stdin: { contents: `
    import { markdownToHtmlDocument } from './src/main/htmlReport'
    import { buildEvidenceSourceNameMap, reportMarkdownForDisplay } from './src/shared/reportDisplay'
    import { readMaterialInsightRows, selectMaterialInsightScope, selectOwnMaterialInsightScope, materialInsightFingerprint, buildSceneCatalog } from './src/renderer/src/materialInsights'
    import { readMaterialInsightResult } from './src/renderer/src/materialInsightWorkflow'
    export async function render(project) {
      const rows=readMaterialInsightRows(project.sources)
      const scope=selectOwnMaterialInsightScope(rows,project.selectedMaterialProducts || [])
      const sceneScope=selectMaterialInsightScope(rows,project.selectedMaterialProducts || [])
      const insight=scope.needsSelection?null:readMaterialInsightResult(project.taskJournal,project.analysisSessionId,materialInsightFingerprint(scope.rows,scope.selectedProducts))
      const htmlInsight=insight?{...insight,mappings:[],missingSellingPointRows:[],items:insight.items.map(item=>({...item,evidenceTotal:item.evidence.length,evidence:item.evidence.slice(0,30).map(e=>({...e,rawDescription:e.rawDescription.length>500?e.rawDescription.slice(0,500)+'…':e.rawDescription,evidenceSnippet:e.evidenceSnippet.length>300?e.evidenceSnippet.slice(0,300)+'…':e.evidenceSnippet}))}))}:undefined
      const scenes=sceneScope.needsSelection?[]:buildSceneCatalog(rows.filter(row=>sceneScope.selectedProducts.includes(row.product)||/竞品|竞对/u.test(row.attribution)))
      const markdown=reportMarkdownForDisplay(project.reportMarkdown,buildEvidenceSourceNameMap(project.cleanDetails))
      return {html:await markdownToHtmlDocument(markdown,htmlInsight,insight?'ready':'missing',scenes),wordCount:insight?.items.length || 0,materialCount:insight?.totalMaterials || 0}
    }
  `, resolveDir: root, loader: 'ts' },
  bundle: true, platform: 'node', format: 'cjs', write: false, logLevel: 'warning'
}).outputFiles[0].text
const renderer = new Module(path.join(root, 'scripts', 'offline-report-renderer.cjs'), module)
renderer.filename = path.join(root, 'scripts', 'offline-report-renderer.cjs')
renderer.paths = module.paths
renderer._compile(compiled, renderer.filename)
renderer.exports.render(project).then(result => {
  if (hash(fs.readFileSync(projectFile)) !== hash(raw)) throw Error('Project changed during rendering; rerun from a stable snapshot')
  fs.mkdirSync(path.dirname(destination), { recursive: true })
  fs.writeFileSync(destination, result.html, { flag: 'wx' })
  console.log(JSON.stringify({output:destination,bytes:Buffer.byteLength(result.html),reportCharacters:project.reportMarkdown.length,wordCount:result.wordCount,materialCount:result.materialCount,verifiedBlobs:blobs.size,projectSha256:hash(raw),modelRequests:0}))
}).catch(error => { console.error(error.message); process.exitCode = 1 })
