from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new)

modules = Path('product-operation-report-app/src/renderer/src/modules.ts')
text = modules.read_text(encoding='utf-8')
text = replace_once(
    text,
    "import { REPORT_MODULES_V2, SOURCE_KIND_LABELS } from '../../shared/types'\n",
    "import { REPORT_MODULES_V2, SOURCE_KIND_LABELS } from '../../shared/types'\nimport { collectAffectedModuleKeys } from './moduleDependencyResolver'\n",
    'modules resolver import'
)
old_retry = """export function retryScopeForModules(
  modules: ReportModule[],
  states: Partial<Record<ModuleKey, ModuleRunState>>,
  requestedKey: ModuleKey
): Set<ModuleKey> {
  const affected = new Set<ModuleKey>([requestedKey])
  for (const module of modules) {
    if (states[module.key]?.status === 'failed') affected.add(module.key)
  }
  let changed = true
  while (changed) {
    changed = false
    for (const module of modules) {
      if (!affected.has(module.key) && module.dependsOn.some((dependency) => affected.has(dependency))) {
        affected.add(module.key)
        changed = true
      }
    }
  }
  return affected
}
"""
new_retry = """export function retryScopeForModules(
  modules: ReportModule[],
  states: Partial<Record<ModuleKey, ModuleRunState>>,
  requestedKey: ModuleKey
): Set<ModuleKey> {
  const seeds = new Set<ModuleKey>([requestedKey])
  for (const module of modules) {
    if (states[module.key]?.status === 'failed') seeds.add(module.key)
  }
  return collectAffectedModuleKeys(modules, seeds)
}
"""
text = replace_once(text, old_retry, new_retry, 'retry scope resolver delegation')
modules.write_text(text, encoding='utf-8')

store = Path('product-operation-report-app/src/renderer/src/store.ts')
text = store.read_text(encoding='utf-8')
text = replace_once(
    text,
    "import { inferSourcePlatform } from './sourceMetadata'\n",
    "import { inferSourcePlatform } from './sourceMetadata'\nimport { buildModuleExecutionBatches } from './moduleDependencyResolver'\n",
    'store resolver import'
)
old_loop = """    for (const wave of [1, 2, 3] as const) {
      if (!isCurrentSession() || get().phase !== 'analyzing') return
      const runnable = REPORT_MODULES.filter((module) => module.wave === wave)
      get()._post('assistant', `正在执行第${wave}/3波：${runnable.map((module) => `M${module.id} ${module.title}`).join('、')}`, 'narration')
      const results = await Promise.allSettled(runnable.map((module) => runModule(module)))
      for (const [index, result] of results.entries()) {
        if (result.status !== 'rejected') continue
        const module = runnable[index]
        const message = friendlyError(result.reason)
        const taskId = `${sessionId}:module:v2:${module.key}`
        updateModuleState(module.key, { status: 'failed', message, updatedAt: new Date().toISOString() })
        set((state) => ({
          ...writeRuntimeTaskState(state.taskJournal, state.taskRecords, taskId, {
            kind: 'module', status: 'failed', moduleKey: module.key
          })
        }))
      }
    }
"""
new_loop = """    const executionBatches = buildModuleExecutionBatches(REPORT_MODULES)
    for (const [batchIndex, runnable] of executionBatches.entries()) {
      if (!isCurrentSession() || get().phase !== 'analyzing') return
      get()._post(
        'assistant',
        `正在执行第${batchIndex + 1}/${executionBatches.length}波：${runnable.map((module) => `M${module.id} ${module.title}`).join('、')}`,
        'narration'
      )
      const results = await Promise.allSettled(runnable.map((module) => runModule(module)))
      for (const [index, result] of results.entries()) {
        if (result.status !== 'rejected') continue
        const module = runnable[index]
        const message = friendlyError(result.reason)
        const taskId = `${sessionId}:module:v2:${module.key}`
        updateModuleState(module.key, { status: 'failed', message, updatedAt: new Date().toISOString() })
        set((state) => ({
          ...writeRuntimeTaskState(state.taskJournal, state.taskRecords, taskId, {
            kind: 'module', status: 'failed', moduleKey: module.key
          })
        }))
      }
    }
"""
text = replace_once(text, old_loop, new_loop, 'store dependency-derived execution batches')
store.write_text(text, encoding='utf-8')
