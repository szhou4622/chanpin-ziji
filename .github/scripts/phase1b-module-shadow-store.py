from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new)

store = Path('product-operation-report-app/src/renderer/src/store.ts')
text = store.read_text(encoding='utf-8')

text = replace_once(
    text,
    "import { completeModuleAsInsufficient } from './store/moduleOutcome'\n",
    """import { completeModuleAsInsufficient } from './store/moduleOutcome'
import {
  failCurrentRunningModuleShadowTask,
  finishModuleShadowTask,
  startModuleShadowTask,
  type ModuleShadowOutcome
} from './store/moduleTaskShadow'
""",
    'shadow helper import'
)

text = replace_once(
    text,
    """    const moduleByKey = new Map(REPORT_MODULES.map((module) => [module.key, module]))
    const runModule = async (module: typeof REPORT_MODULES[number]): Promise<void> => {
""",
    """    const moduleByKey = new Map(REPORT_MODULES.map((module) => [module.key, module]))
    const activeModuleShadowTaskIds = new Map<ModuleKey, string>()
    const runModule = async (module: typeof REPORT_MODULES[number]): Promise<void> => {
""",
    'active shadow task map'
)

text = replace_once(
    text,
    """      const savedState = readRuntimeTaskState(get().taskJournal, get().taskRecords, savedTaskId)
      const saved = savedState.journal
      const savedTask = savedState.task
      const completeAsInsufficient = async (message: string, inputFingerprint?: string): Promise<string> => {
""",
    """      const savedState = readRuntimeTaskState(get().taskJournal, get().taskRecords, savedTaskId)
      const saved = savedState.journal
      const savedTask = savedState.task
      let shadowTaskId: string | undefined
      const finishShadowState = (
        state: StoreState,
        taskRecords: Record<string, TaskRecord>,
        outcome: ModuleShadowOutcome,
        updatedAt: string
      ): { taskRecords: Record<string, TaskRecord>; currentTaskByLogicalKey: TaskCurrentIndex } => {
        if (!shadowTaskId) {
          return { taskRecords, currentTaskByLogicalKey: state.currentTaskByLogicalKey }
        }
        try {
          const shadow = finishModuleShadowTask(
            taskRecords,
            state.currentTaskByLogicalKey,
            savedTaskId,
            shadowTaskId,
            outcome,
            updatedAt
          )
          activeModuleShadowTaskIds.delete(module.key)
          return shadow
        } catch {
          activeModuleShadowTaskIds.delete(module.key)
          shadowTaskId = undefined
          return { taskRecords, currentTaskByLogicalKey: state.currentTaskByLogicalKey }
        }
      }
      const completeAsInsufficient = async (message: string, inputFingerprint?: string): Promise<string> => {
""",
    'shadow task local state'
)

old_insufficient = """        set((state) => {
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
"""
new_insufficient = """        set((state) => {
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
          const shadow = finishShadowState(
            state,
            outcome.taskRecords,
            { executionStatus: 'SUCCEEDED', resultStatus: 'INSUFFICIENT' },
            updatedAt
          )
          return {
            taskJournal: outcome.taskJournal,
            taskRecords: shadow.taskRecords,
            currentTaskByLogicalKey: shadow.currentTaskByLogicalKey,
            moduleStates: { ...state.moduleStates, [module.key]: outcome.moduleState }
          }
        })
"""
text = replace_once(text, old_insufficient, new_insufficient, 'insufficient shadow completion')

text = replace_once(
    text,
    """      if (module.key === 'benchmark-brands') {
        const message = '暂无分析：对标联网模块仅保留为旧版兼容，不参与v2六模块分析。'
        await completeAsInsufficient(message)
        return
      }
      const moduleTaskContext = {
""",
    """      if (module.key === 'benchmark-brands') {
        const message = '暂无分析：对标联网模块仅保留为旧版兼容，不参与v2六模块分析。'
        await completeAsInsufficient(message)
        return
      }
      const shadowStartedAt = new Date().toISOString()
      try {
        set((state) => {
          const shadow = startModuleShadowTask(
            state.taskRecords,
            state.currentTaskByLogicalKey,
            {
              logicalKey: savedTaskId,
              payloadKey: savedTaskId,
              moduleKey: module.key,
              inputFingerprint,
              instanceToken: crypto.randomUUID(),
              now: shadowStartedAt
            }
          )
          shadowTaskId = shadow.taskId
          activeModuleShadowTaskIds.set(module.key, shadow.taskId)
          return {
            taskRecords: shadow.taskRecords,
            currentTaskByLogicalKey: shadow.currentTaskByLogicalKey
          }
        })
        void window.api.saveLastProject(buildProjectSnapshot(get())).catch(() => undefined)
      } catch {
        // Shadow lifecycle is observational in Phase 1B and must never block production execution.
        shadowTaskId = undefined
        activeModuleShadowTaskIds.delete(module.key)
      }
      const moduleTaskContext = {
""",
    'start model shadow task'
)

old_request_failure = """      if (!result.ok || !result.text.trim()) {
        const message = result.error || '模块没有返回内容'
        updateModuleState(module.key, { status: 'failed', message, updatedAt: new Date().toISOString() })
        set((state) => ({
          ...writeRuntimeTaskState(state.taskJournal, state.taskRecords, savedTaskId, {
            kind: 'module', status: 'failed', output: result.text, inputFingerprint, moduleKey: module.key
          })
        }))
        return
      }
"""
new_request_failure = """      if (!result.ok || !result.text.trim()) {
        const message = result.error || '模块没有返回内容'
        const updatedAt = new Date().toISOString()
        updateModuleState(module.key, { status: 'failed', message, updatedAt })
        set((state) => {
          const legacy = writeRuntimeTaskState(state.taskJournal, state.taskRecords, savedTaskId, {
            kind: 'module', status: 'failed', output: result.text, inputFingerprint, moduleKey: module.key, updatedAt
          })
          const shadow = finishShadowState(
            state,
            legacy.taskRecords,
            isUserStop(result.error)
              ? { executionStatus: 'CANCELLED', errorClass: 'USER_STOP' }
              : { executionStatus: 'FAILED', errorClass: 'MODEL_REQUEST_FAILED' },
            updatedAt
          )
          return {
            taskJournal: legacy.taskJournal,
            taskRecords: shadow.taskRecords,
            currentTaskByLogicalKey: shadow.currentTaskByLogicalKey
          }
        })
        return
      }
"""
text = replace_once(text, old_request_failure, new_request_failure, 'request failure shadow completion')

old_validation_failure = """      if (validationErrors.length) {
        const message = validationErrors.join('；')
        updateModuleState(module.key, { status: 'failed', message, updatedAt: new Date().toISOString() })
        set((state) => ({
          ...writeRuntimeTaskState(state.taskJournal, state.taskRecords, savedTaskId, {
            kind: 'module', status: 'failed', output: moduleOutput, inputFingerprint, moduleKey: module.key
          })
        }))
        return
      }
"""
new_validation_failure = """      if (validationErrors.length) {
        const message = validationErrors.join('；')
        const updatedAt = new Date().toISOString()
        updateModuleState(module.key, { status: 'failed', message, updatedAt })
        set((state) => {
          const legacy = writeRuntimeTaskState(state.taskJournal, state.taskRecords, savedTaskId, {
            kind: 'module', status: 'failed', output: moduleOutput, inputFingerprint, moduleKey: module.key, updatedAt
          })
          const shadow = finishShadowState(
            state,
            legacy.taskRecords,
            { executionStatus: 'FAILED', errorClass: 'VALIDATION_FAILED' },
            updatedAt
          )
          return {
            taskJournal: legacy.taskJournal,
            taskRecords: shadow.taskRecords,
            currentTaskByLogicalKey: shadow.currentTaskByLogicalKey
          }
        })
        return
      }
"""
text = replace_once(text, old_validation_failure, new_validation_failure, 'validation failure shadow completion')

old_success = """      set((state) => ({
        artifacts: { ...state.artifacts, [module.id]: moduleOutput },
        ...writeRuntimeTaskState(state.taskJournal, state.taskRecords, savedTaskId, {
          kind: 'module', status: 'complete', output: moduleOutput, inputFingerprint,
          resultStatus: 'VALID', moduleKey: module.key
        })
      }))
      updateModuleState(module.key, { status: 'done', updatedAt: new Date().toISOString() })
"""
new_success = """      const completedAt = new Date().toISOString()
      set((state) => {
        const legacy = writeRuntimeTaskState(state.taskJournal, state.taskRecords, savedTaskId, {
          kind: 'module', status: 'complete', output: moduleOutput, inputFingerprint,
          resultStatus: 'VALID', moduleKey: module.key, updatedAt: completedAt
        })
        const shadow = finishShadowState(
          state,
          legacy.taskRecords,
          { executionStatus: 'SUCCEEDED', resultStatus: 'VALID' },
          completedAt
        )
        return {
          artifacts: { ...state.artifacts, [module.id]: moduleOutput },
          taskJournal: legacy.taskJournal,
          taskRecords: shadow.taskRecords,
          currentTaskByLogicalKey: shadow.currentTaskByLogicalKey
        }
      })
      updateModuleState(module.key, { status: 'done', updatedAt: completedAt })
"""
text = replace_once(text, old_success, new_success, 'success shadow completion')

old_outer = """        const module = runnable[index]
        const message = friendlyError(result.reason)
        const taskId = `${sessionId}:module:v2:${module.key}`
        updateModuleState(module.key, { status: 'failed', message, updatedAt: new Date().toISOString() })
        set((state) => ({
          ...writeRuntimeTaskState(state.taskJournal, state.taskRecords, taskId, {
            kind: 'module', status: 'failed', moduleKey: module.key
          })
        }))
"""
new_outer = """        const module = runnable[index]
        const message = friendlyError(result.reason)
        const taskId = `${sessionId}:module:v2:${module.key}`
        const updatedAt = new Date().toISOString()
        updateModuleState(module.key, { status: 'failed', message, updatedAt })
        const expectedShadowTaskId = activeModuleShadowTaskIds.get(module.key)
        set((state) => {
          const legacy = writeRuntimeTaskState(state.taskJournal, state.taskRecords, taskId, {
            kind: 'module', status: 'failed', moduleKey: module.key, updatedAt
          })
          let shadow = {
            taskRecords: legacy.taskRecords,
            currentTaskByLogicalKey: state.currentTaskByLogicalKey
          }
          if (expectedShadowTaskId && state.currentTaskByLogicalKey[taskId] === expectedShadowTaskId) {
            try {
              shadow = failCurrentRunningModuleShadowTask(
                legacy.taskRecords,
                state.currentTaskByLogicalKey,
                taskId,
                updatedAt,
                'UNHANDLED'
              )
            } catch {
              // Shadow lifecycle remains observational and cannot replace the production failure path.
            }
          }
          activeModuleShadowTaskIds.delete(module.key)
          return {
            taskJournal: legacy.taskJournal,
            taskRecords: shadow.taskRecords,
            currentTaskByLogicalKey: shadow.currentTaskByLogicalKey
          }
        })
"""
text = replace_once(text, old_outer, new_outer, 'outer failure shadow cleanup')

store.write_text(text, encoding='utf-8')
