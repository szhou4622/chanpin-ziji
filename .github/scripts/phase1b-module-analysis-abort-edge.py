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
    """      if (module.key === 'benchmark-brands') {
        const message = '暂无分析：对标联网模块仅保留为旧版兼容，不参与v2六模块分析。'
        await completeAsInsufficient(message)
        return
      }
      const shadowStartedAt = new Date().toISOString()
""",
    """      if (module.key === 'benchmark-brands') {
        const message = '暂无分析：对标联网模块仅保留为旧版兼容，不参与v2六模块分析。'
        await completeAsInsufficient(message)
        return
      }
      if (analysisAbortGroup.isAborted()) return
      const shadowStartedAt = new Date().toISOString()
""",
    'cancel before new model request'
)

text = replace_once(
    text,
    """          )
          if (!corrected.ok || !corrected.text.trim()) break
          result = corrected
          moduleOutput = module.key === 'material-review'
""",
    """          )
          if (!corrected.ok || !corrected.text.trim()) {
            result = corrected
            break
          }
          result = corrected
          moduleOutput = module.key === 'material-review'
""",
    'retain validation retry stop result'
)

text = replace_once(
    text,
    """      }
      if (validationErrors.length) {
        const message = validationErrors.join('；')
        const updatedAt = new Date().toISOString()
""",
    """      }
      if (validationErrors.length && isUserStop(result.error)) {
        const message = result.error || '已停止'
        const updatedAt = new Date().toISOString()
        updateModuleState(module.key, { status: 'failed', message, updatedAt })
        set((state) => {
          const legacy = writeRuntimeTaskState(state.taskJournal, state.taskRecords, savedTaskId, {
            kind: 'module', status: 'failed', output: moduleOutput, inputFingerprint, moduleKey: module.key, updatedAt
          })
          const shadow = finishShadowState(
            state,
            legacy.taskRecords,
            { executionStatus: 'CANCELLED', errorClass: 'USER_STOP' },
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
      if (validationErrors.length) {
        const message = validationErrors.join('；')
        const updatedAt = new Date().toISOString()
""",
    'validation retry cancellation outcome'
)

store.write_text(text, encoding='utf-8')
