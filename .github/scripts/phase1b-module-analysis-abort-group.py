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
    "import { isTemporaryReservationContention, planCleaningConcurrency } from './store/cleaning'\n",
    """import { isTemporaryReservationContention, planCleaningConcurrency } from './store/cleaning'
import { createAbortGroup } from './store/abortGroup'
""",
    'abort group import'
)

text = replace_once(
    text,
    """    const sourceCountV1 = topLevelSourceCount(analysisSources)
    const imageCountV1 = sourceImageCount(analysisSources)
    const activeReportSessionId = sessionId
    const updateModuleState = (key: ModuleKey, state: ModuleRunState): void => {
""",
    """    const sourceCountV1 = topLevelSourceCount(analysisSources)
    const imageCountV1 = sourceImageCount(analysisSources)
    const activeReportSessionId = sessionId
    const analysisAbortGroup = createAbortGroup()
    set({ abortFn: () => analysisAbortGroup.abortAll() })
    const updateModuleState = (key: ModuleKey, state: ModuleRunState): void => {
""",
    'analysis parent abort group'
)

text = replace_once(
    text,
    """    const persistCompletedModuleState = async (module: typeof REPORT_MODULES[number]): Promise<void> => {
      const persisted = await persistCompletedModuleSnapshot(
        () => window.api.saveLastProject(buildProjectSnapshot(get()))
      )
      if (!persisted.ok && isCurrentSession()) {
        get()._post(
          'assistant',
          completedModulePersistenceWarning(
            `M${module.id} ${module.title}`,
            friendlyError(persisted.error)
          ),
          'error'
        )
      }
    }
    const runModule = async (module: typeof REPORT_MODULES[number]): Promise<void> => {
""",
    """    const persistCompletedModuleState = async (module: typeof REPORT_MODULES[number]): Promise<void> => {
      const persisted = await persistCompletedModuleSnapshot(
        () => window.api.saveLastProject(buildProjectSnapshot(get()))
      )
      if (!persisted.ok && isCurrentSession()) {
        get()._post(
          'assistant',
          completedModulePersistenceWarning(
            `M${module.id} ${module.title}`,
            friendlyError(persisted.error)
          ),
          'error'
        )
      }
    }
    const finishCancelledAnalysis = async (): Promise<void> => {
      if (!isCurrentSession()) return
      set({ phase: 'checkpoint1', abortFn: null })
      get()._post(
        'assistant',
        '已停止6模块分析。已经完成的模块结果已保留，未完成或已取消的模块下次继续时会重新执行；本次不会再启动后续波次。',
        'narration'
      )
      try {
        await window.api.saveLastProject(buildProjectSnapshot(get()))
      } catch (error) {
        get()._post(
          'assistant',
          `停止状态已经生效，但本地项目快照保存失败：${friendlyError(error)}。当前窗口结果仍保留，请暂时不要关闭软件。`,
          'error'
        )
      }
    }
    const runModule = async (module: typeof REPORT_MODULES[number]): Promise<void> => {
""",
    'cancelled analysis completion helper'
)

text = replace_once(
    text,
    """      const savedState = readRuntimeTaskState(get().taskJournal, get().taskRecords, savedTaskId)
      const saved = savedState.journal
      const savedTask = savedState.task
      let shadowTaskId: string | undefined
""",
    """      const savedState = readRuntimeTaskState(get().taskJournal, get().taskRecords, savedTaskId)
      const saved = savedState.journal
      const savedTask = savedState.task
      const setModuleAbort = analysisAbortGroup.createRegistrar()
      let shadowTaskId: string | undefined
""",
    'per-module abort registrar'
)

text = replace_once(
    text,
    """      let result = await runModelRetry(
        messages,
        () => {},
        (fn) => {
          if (isCurrentSession()) set({ abortFn: fn })
        },
        (attempt) => {
""",
    """      let result = await runModelRetry(
        messages,
        () => {},
        setModuleAbort,
        (attempt) => {
""",
    'primary module grouped abort'
)

text = replace_once(
    text,
    """            () => {},
            (fn) => {
              if (isCurrentSession()) set({ abortFn: fn })
            },
            undefined,
            1,
            { ...moduleTaskContext, stepId: `${module.key}-validation-retry-${validationPass}` }
""",
    """            () => {},
            setModuleAbort,
            undefined,
            1,
            { ...moduleTaskContext, stepId: `${module.key}-validation-retry-${validationPass}` }
""",
    'validation retry grouped abort'
)

text = replace_once(
    text,
    """    const executionBatches = buildModuleExecutionBatches(REPORT_MODULES)
    for (const [batchIndex, runnable] of executionBatches.entries()) {
      if (!isCurrentSession() || get().phase !== 'analyzing') return
      get()._post(
""",
    """    const executionBatches = buildModuleExecutionBatches(REPORT_MODULES)
    for (const [batchIndex, runnable] of executionBatches.entries()) {
      if (!isCurrentSession() || get().phase !== 'analyzing') return
      if (analysisAbortGroup.isAborted()) {
        await finishCancelledAnalysis()
        return
      }
      get()._post(
""",
    'pre-wave cancellation gate'
)

text = replace_once(
    text,
    """          return {
            taskJournal: legacy.taskJournal,
            taskRecords: shadow.taskRecords,
            currentTaskByLogicalKey: shadow.currentTaskByLogicalKey
          }
        })
      }
    }
    if (!isCurrentSession()) return
""",
    """          return {
            taskJournal: legacy.taskJournal,
            taskRecords: shadow.taskRecords,
            currentTaskByLogicalKey: shadow.currentTaskByLogicalKey
          }
        })
      }
      if (analysisAbortGroup.isAborted()) {
        await finishCancelledAnalysis()
        return
      }
    }
    if (!isCurrentSession()) return
""",
    'post-wave cancellation gate'
)

store.write_text(text, encoding='utf-8')
