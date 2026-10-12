// Exercise the real renderer store, preload IPC, main process, proxy and exports.
// Supply a private, bounded test authorization; never copy production credentials.
const fs = require('node:fs')
const path = require('node:path')
const crypto = require('node:crypto')
const { pathToFileURL } = require('node:url')
const { spawnSync } = require('node:child_process')
const { buildSync } = require('esbuild')

const args = process.argv.slice(2)
if (args.includes('--help')) {
  console.log('Usage: node scripts/run-full-report-e2e.cjs --source-profile DIR --authorization FILE --output DIR [--resume]')
  process.exit(0)
}
const option = flag => { const index = args.indexOf(flag); if (index < 0 || !args[index + 1]) throw Error('Missing ' + flag); return path.resolve(args[index + 1]) }
const root = path.resolve(__dirname, '..')
const source = option('--source-profile')
const authorization = option('--authorization')
const output = option('--output')
const work = path.dirname(authorization)
const profile = path.join(work, 'profile')
const resume = args.includes('--resume')
if (!work.startsWith(path.join(root, '.codex-runtime') + path.sep) || source === profile || (fs.existsSync(profile) && !resume)) throw Error('Use a new isolated workspace test profile, or explicitly resume it')
const auth = JSON.parse(fs.readFileSync(authorization, 'utf8'))
if (!auth.marker.startsWith('por-report-e2e-') || auth.points !== 2000 || !/^[A-F0-9]{16}$/.test(auth.codeId)) throw Error('A bounded report test authorization is required')
const snapshot = fs.readFileSync(path.join(source, 'last-project.json'))
const project = JSON.parse(snapshot).project
if (!project || project.phase !== 'checkpoint1' || project.cleanDetails.length !== project.sources.length) throw Error('Snapshot must contain completed cleaning and await analysis')
fs.mkdirSync(path.join(profile, 'project-data', 'blobs'), { recursive: true })
fs.mkdirSync(output, { recursive: true })
const hashes = new Set()
function copyBlobs(value) {
  if (!value || typeof value !== 'object') return
  if (value.$blob) {
    if (!/^[a-f0-9]{64}$/.test(value.$blob)) throw Error('Invalid snapshot blob reference')
    if (hashes.has(value.$blob)) return
    const bytes = fs.readFileSync(path.join(source, 'project-data', 'blobs', value.$blob + '.txt'))
    if (bytes.length !== value.bytes || crypto.createHash('sha256').update(bytes).digest('hex') !== value.$blob) throw Error('Snapshot blob failed checksum')
    fs.writeFileSync(path.join(profile, 'project-data', 'blobs', value.$blob + '.txt'), bytes, { flag: 'wx' })
    hashes.add(value.$blob)
    return
  }
  Object.values(value).forEach(copyBlobs)
}
const contextFile = path.join(work, 'context.json')
const snapshotHash = crypto.createHash('sha256').update(snapshot).digest('hex')
if (resume) {
  const context = JSON.parse(fs.readFileSync(contextFile, 'utf8'))
  if (context.marker !== auth.marker || context.sourceSnapshotSha256 !== snapshotHash) throw Error('Resume identity or input snapshot changed')
} else {
  copyBlobs(project)
  fs.writeFileSync(path.join(profile, 'last-project.json'), snapshot, { flag: 'wx' })
  fs.writeFileSync(contextFile, JSON.stringify({ marker: auth.marker, sourceSnapshotSha256: snapshotHash }), { flag: 'wx' })
}

const rendererSource = `
  import React from 'react'
  import { createRoot } from 'react-dom/client'
  import App from './src/renderer/src/App'
  import AppErrorBoundary from './src/renderer/src/components/AppErrorBoundary'
  import { useStore } from './src/renderer/src/store'
  import { validateReportEvidenceLinks } from './src/renderer/src/validate'
  import { readMaterialInsightResult } from './src/renderer/src/materialInsightWorkflow'
  import { readMaterialInsightRows, selectOwnMaterialInsightScope, materialInsightFingerprint } from './src/renderer/src/materialInsights'
  import './src/renderer/src/styles.css'
  import './src/renderer/src/styles/contact-wallet.css'
  window.__porStore = useStore
  window.__porAudit = () => {
    const s = useStore.getState()
    const scope = selectOwnMaterialInsightScope(readMaterialInsightRows(s.sources), s.selectedMaterialProducts)
    const insight = readMaterialInsightResult(s.taskJournal, s.analysisSessionId, materialInsightFingerprint(scope.rows, scope.selectedProducts))
    const evidence = validateReportEvidenceLinks(s.reportMarkdown, s.cleanedData)
    const ownIds = new Set(s.sources.filter(source=>source.attribution==='自有数据').map(source=>source.id))
    return { initialized: s.initialized, phase: s.phase, sources: s.sources.length, cleaned: s.cleanDetails.length,
      modules: Object.fromEntries(Object.entries(s.moduleStates).map(([key,v])=>[key,{status:v.status,message:v.message}])),
      reportChars: s.reportMarkdown.length, wordCloudItems: insight?.items.length || 0,
      wordCloudOwnOnly: Boolean(insight && insight.mappings.every(mapping=>ownIds.has(mapping.sourceId))),
      wordCloudEvidenceRestored: Boolean(insight?.items.every(item=>item.evidence.length>0 && item.evidence.every(mapping=>ownIds.has(mapping.sourceId)))),
      materialRows: scope.rows.length, evidenceErrors: evidence.errors,
      linkedEvidenceIds: evidence.linkedIds, exportStatus: s.exportStatus, exportPath: s.lastExportPath,
      confirmedTasks: Object.values(s.taskJournal).filter(t=>t.billingConfirmed).length }
  }
  createRoot(document.getElementById('root')).render(<AppErrorBoundary><App /></AppErrorBoundary>)
`
buildSync({ stdin: { contents: rendererSource, resolveDir: root, loader: 'tsx' },
  bundle: true, platform: 'browser', jsx: 'automatic', loader: { '.png': 'dataurl' },
  define: { 'process.env.NODE_ENV': '"production"' }, outfile: path.join(work, 'renderer.js'), logLevel: 'warning' })
fs.writeFileSync(path.join(work, 'index.html'), '<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="renderer.css"></head><body><div id="root"></div><script src="renderer.js"></script></body></html>')

const mainSource = `
  import { app, BrowserWindow, dialog } from 'electron'
  import { writeStoredMachineCode } from './src/main/licenseVault'
  import { randomBytes } from 'node:crypto'
  import { readFileSync, writeFileSync, existsSync, statSync } from 'node:fs'
  import { join, extname } from 'node:path'
  const profile = ${JSON.stringify(profile)}
  const output = ${JSON.stringify(output)}
  const authPath = ${JSON.stringify(authorization)}
  app.setPath('userData', profile)
  BrowserWindow.prototype.show = function() {}
  BrowserWindow.prototype.focus = function() {}
  dialog.showSaveDialog = async (options) => {
    const extension = extname(options.defaultPath || '')
    if (!['.html','.docx','.md'].includes(extension)) throw Error('Unexpected export format')
    const filePath = join(output, '产品经营报告-完整验证' + extension)
    if (existsSync(filePath)) throw Error('Refuse to overwrite an existing report')
    return { canceled: false, filePath }
  }
  const pause = ms => new Promise(resolve=>setTimeout(resolve,ms))
  let main
  app.whenReady().then(async () => {
    if (!existsSync(join(profile,'device-vault.bin'))) writeStoredMachineCode(randomBytes(16).toString('hex'))
    require(${JSON.stringify(path.join(root, 'out', 'main', 'index.js'))})
    for (let i=0;i<120;i++) {
      main = BrowserWindow.getAllWindows()[0]
      if (main && await main.webContents.executeJavaScript('Boolean(window.api && window.__porStore)').catch(()=>false)) break
      await pause(250)
    }
    if (!main) throw Error('Application window did not initialize')
    for (let i=0;i<120;i++) { if(await main.webContents.executeJavaScript('window.__porStore.getState().initialized')) break; await pause(250) }
    if (!await main.webContents.executeJavaScript('window.__porStore.getState().initialized')) throw Error('Application startup did not finish')
    const auth = JSON.parse(readFileSync(authPath,'utf8'))
    let status = await main.webContents.executeJavaScript('window.api.refreshActivationStatus()')
    if (!status.activated) {
      const activated = await main.webContents.executeJavaScript('window.api.activate(' + JSON.stringify(auth.activationCode) + ')')
      if (!activated.ok) throw Error('Test authorization did not activate: ' + activated.status.authorizationState)
      status = activated.status
    }
    if (status.licenseId !== auth.codeId || status.unlimited || status.offline || status.requiresRevalidation) throw Error('Active authorization does not match the bounded online test account')
    await main.webContents.executeJavaScript('(async()=>{const s=window.__porStore.getState(); await s.saveSettings({...s.settings,privacyAccepted:true,privacyEndpoint:s.settings.managedModel.baseURL}); return true})()')
    const before = await main.webContents.executeJavaScript('window.__porAudit()')
    if(!['checkpoint1','done'].includes(before.phase) || before.sources !== before.cleaned) throw Error('Clean snapshot was not restored')
    console.log(JSON.stringify({stage:'restored',sources:before.sources,cleaned:before.cleaned}))
    if(before.phase==='done') await main.webContents.executeJavaScript('window.__porStore.setState({phase:"checkpoint1"})')
    const usagePath=join(profile,'token-usage.jsonl')
    const priorEventCount=existsSync(usagePath)?readFileSync(usagePath,'utf8').trim().split(/\\r?\\n/).length:0
    await main.webContents.executeJavaScript('window.__porFinished=false;window.__porStore.getState().confirmCheckpoint().then(()=>{window.__porFinished=true},()=>{window.__porFinished=true});true')
    let previous = ''
    const deadline = Date.now()+30*60*1000
    while(Date.now()<deadline){
      const state=await main.webContents.executeJavaScript('window.__porAudit()')
      const progress=JSON.stringify({stage:'analysis',phase:state.phase,modules:state.modules,wordCloudItems:state.wordCloudItems})
      if(progress!==previous){console.log(progress);previous=progress}
      if(await main.webContents.executeJavaScript('window.__porFinished'))break
      await pause(3000)
    }
    const complete=await main.webContents.executeJavaScript('window.__porAudit()')
    writeFileSync(join(output,'verification.json'),JSON.stringify(complete,null,2))
    const states=Object.values(complete.modules)
    if(complete.phase!=='done'||states.length!==6||states.some(v=>!['done','skipped'].includes(v.status))||complete.reportChars<1000||complete.wordCloudItems<1||!complete.wordCloudOwnOnly||!complete.wordCloudEvidenceRestored||complete.evidenceErrors.length) throw Error('Full report completion or evidence validation failed')
    for(const format of ['md','html','docx']){
      await main.webContents.executeJavaScript('window.__porStore.getState().exportReport('+JSON.stringify(format)+')')
      const status=await main.webContents.executeJavaScript('window.__porAudit()')
      const expectedPath=join(output,'产品经营报告-完整验证.'+format)
      if(status.exportPath!==expectedPath||!status.exportStatus.startsWith('已导出')||!existsSync(expectedPath)||statSync(expectedPath).size<100) throw Error('Export failed: '+format)
      console.log(JSON.stringify({stage:'export',format,bytes:statSync(status.exportPath).size}))
    }
    await new Promise(resolve=>{main.webContents.once('did-finish-load',resolve);main.webContents.reload()})
    for(let i=0;i<120;i++){if(await main.webContents.executeJavaScript('Boolean(window.__porStore?.getState().initialized)').catch(()=>false))break;await pause(250)}
    const reopened=await main.webContents.executeJavaScript('window.__porAudit()')
    if(reopened.phase!=='done'||reopened.reportChars!==complete.reportChars||reopened.wordCloudItems!==complete.wordCloudItems||!reopened.wordCloudOwnOnly||!reopened.wordCloudEvidenceRestored)throw Error('Saved report did not restore')
    const events=readFileSync(join(profile,'token-usage.jsonl'),'utf8').trim().split(/\\r?\\n/).map(line=>JSON.parse(line))
    if(events.some(event=>event.taskType==='source_clean'))throw Error('Already-cleaned data was unexpectedly reprocessed')
    const newEvents=events.slice(priorEventCount)
    if(${JSON.stringify(resume)} && newEvents.some(event=>event.eventType==='started' && !event.taskKey.includes(':material-insight:v1:')))throw Error('Completed core modules were unexpectedly reprocessed')
    const audit={...complete,reopenPassed:true,exports:['md','html','docx'],recleanedRequests:0,
      resumedWithOnlyWordCloudRequests:${JSON.stringify(resume)},newModelRequests:newEvents.filter(event=>event.eventType==='started').length,
      finalRequests:events.filter(event=>event.eventType==='final').map(({taskType,status,inputTokens,outputTokens,reasoningTokens,outputChars})=>({taskType,status,inputTokens,outputTokens,reasoningTokens,outputChars}))}
    writeFileSync(join(output,'verification.json'),JSON.stringify(audit,null,2))
    console.log(JSON.stringify({stage:'complete',reopenPassed:true,reportChars:complete.reportChars,wordCloudItems:complete.wordCloudItems}))
    main.destroy();app.exit(0)
  }).catch(async error=>{
    console.error('FULL_REPORT_E2E_FAILED',error instanceof Error?error.message:'unknown')
    if(main&&!main.isDestroyed()){await main.webContents.executeJavaScript('window.__porStore?.getState().abort()').catch(()=>{});main.destroy()}
    app.exit(1)
  })
`
buildSync({ stdin: { contents: mainSource, resolveDir: root, loader: 'ts' }, bundle: true,
  platform: 'node', format: 'cjs', external: ['electron', path.join(root, 'out', 'main', 'index.js')],
  outfile: path.join(work, 'main.cjs'), logLevel: 'warning' })
const env = { ...process.env, PRODUCT_REPORT_ALLOW_DEV_OVERRIDES: '1', PRODUCT_REPORT_DEV_FORCE_PROXY: '1',
  PRODUCT_REPORT_DEV_USER_DATA_DIR: profile, ELECTRON_RENDERER_URL: pathToFileURL(path.join(work, 'index.html')).href }
delete env.ELECTRON_RUN_AS_NODE
console.log(JSON.stringify({stage:'prepared',verifiedBlobs:hashes.size,sourceSnapshotSha256:crypto.createHash('sha256').update(snapshot).digest('hex')}))
const result = spawnSync(require('electron'), [path.join(work, 'main.cjs')], { cwd:root, env, stdio:'inherit', windowsHide:true })
process.exitCode = result.status ?? 1
