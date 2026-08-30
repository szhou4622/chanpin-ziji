from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new)

path = Path('product-operation-report-app/src/renderer/src/store.ts')
text = path.read_text(encoding='utf-8')
text = replace_once(
    text,
    "import { readRuntimeTaskState, removeRuntimeTaskState, writeRuntimeTaskState } from './store/taskJournalAdapter'\n",
    "import { readRuntimeTaskState, removeRuntimeTaskState, writeRuntimeTaskState } from './store/taskJournalAdapter'\nimport { completeModuleAsInsufficient } from './store/moduleOutcome'\n",
    'module outcome import'
)
old_start = """    const moduleByKey = new Map(REPORT_MODULES.map((module) => [module.key, module]))
    const runModule = async (module: typeof REPORT_MODULES[number]): Promise<void> => {
      if (!isCurrentSession()) return
      const skippedReason = sufficiency.skipped.get(module.key)
      if (skippedReason) {
        updateModuleState(module.key, { status: 'skipped', message: skippedReason, updatedAt: new Date().toISOString() })
        return
      }
      const savedTaskId = `${sessionId}:module:v2:${module.key}`
      const savedState = readRuntimeTaskState(get().taskJournal, get().taskRecords, savedTaskId)
      const saved = savedState.journal
      const savedTask = savedState.task
"""
new_start = """    const moduleByKey = new Map(REPORT_MODULES.map((module) => [module.key, module]))
    const runModule = async (module: typeof REPORT_MODULES[number]): Promise<void> => {
      if (!isCurrentSession()) return
      const savedTaskId = `${sessionId}:module:v2:${module.key}`
      const savedState = readRuntimeTaskState(get().taskJournal, get().taskRecords, savedTaskId)
      const saved = savedState.journal
      const savedTask = savedState.task
      const completeAsInsufficient = async (message: string, inputFingerprint?: string): Promise<string> => {
        const updatedAt = new Date().toISOString()
        let output = message
        set((state) => {
          const outcome = completeModuleAsInsufficient(
            state.taskJournal,
            state.taskRecords,
            savedTaskId,
            module.key,
            message,
            updatedAt,
            inputFingerprint
          )
          output = outcome.output
          return {
            taskJournal: outcome.taskJournal,
            taskRecords: outcome.taskRecords,
            moduleStates: { ...state.moduleStates, [module.key]: outcome.moduleState }
          }
        })
        await window.api.saveLastProject(buildProjectSnapshot(get()))
        return output
      }
      const skippedReason = sufficiency.skipped.get(module.key)
      if (skippedReason) {
        await completeAsInsufficient(skippedReason)
        return
      }
"""
text = replace_once(text, old_start, new_start, 'runModule canonical skip setup')

old_retained = """        if (retainedState?.status === 'skipped') return
"""
new_retained = """        if (retainedState?.status === 'skipped') {
          if (!savedTask && retainedState.message) await completeAsInsufficient(retainedState.message)
          return
        }
"""
text = replace_once(text, old_retained, new_retained, 'backfill retained skipped task')

old_dependency = """      if (module.dependsOn.length > 0 && module.requiredSources.length === 0 && upstream.length === 0) {
        const message = `暂无分析：缺少${module.dependsOn.map((key) => moduleByTitle(key)).join('、')}的可用结果。`
        updateModuleState(module.key, { status: 'skipped', message, updatedAt: new Date().toISOString() })
        return
      }
"""
new_dependency = """      if (module.dependsOn.length > 0 && module.requiredSources.length === 0 && upstream.length === 0) {
        const message = `暂无分析：缺少${module.dependsOn.map((key) => moduleByTitle(key)).join('、')}的可用结果。`
        await completeAsInsufficient(message)
        return
      }
"""
text = replace_once(text, old_dependency, new_dependency, 'dependency-only skip outcome')

old_benchmark = """      if (module.key === 'benchmark-brands') {
        const message = '暂无分析：对标联网模块仅保留为旧版兼容，不参与v2六模块分析。'
        updateModuleState(module.key, { status: 'skipped', message, updatedAt: new Date().toISOString() })
        return
      }
"""
new_benchmark = """      if (module.key === 'benchmark-brands') {
        const message = '暂无分析：对标联网模块仅保留为旧版兼容，不参与v2六模块分析。'
        await completeAsInsufficient(message)
        return
      }
"""
text = replace_once(text, old_benchmark, new_benchmark, 'legacy benchmark skip outcome')

old_model_no_analysis = """      if (isNoAnalysisOutput(moduleOutput)) {
        const output = normalizeNoAnalysisOutput(moduleOutput)
        set((state) => ({
          ...writeRuntimeTaskState(state.taskJournal, state.taskRecords, savedTaskId, {
            kind: 'module', status: 'complete', output, inputFingerprint,
            resultStatus: 'INSUFFICIENT', moduleKey: module.key
          })
        }))
        updateModuleState(module.key, { status: 'skipped', message: output, updatedAt: new Date().toISOString() })
        await window.api.saveLastProject(buildProjectSnapshot(get()))
        return
      }
"""
new_model_no_analysis = """      if (isNoAnalysisOutput(moduleOutput)) {
        await completeAsInsufficient(normalizeNoAnalysisOutput(moduleOutput), inputFingerprint)
        return
      }
"""
text = replace_once(text, old_model_no_analysis, new_model_no_analysis, 'model insufficient outcome')

path.write_text(text, encoding='utf-8')
