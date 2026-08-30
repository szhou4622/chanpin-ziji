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
    "import { removeRuntimeTaskState, writeRuntimeTaskState } from './store/taskJournalAdapter'\n",
    "import { readRuntimeTaskState, removeRuntimeTaskState, writeRuntimeTaskState } from './store/taskJournalAdapter'\n",
    'adapter read import'
)
text = replace_once(
    text,
    """                const batchTaskId = `${sessionId}:source_clean:${s.id}:batch-v7-planned:${batch.context.batchIndex}`
                const savedBatch = get().taskJournal[batchTaskId]
                if (savedBatch?.status === 'complete' && savedBatch.output?.trim()) {
                  batchOutputs[batchPosition] = savedBatch.output
""",
    """                const batchTaskId = `${sessionId}:source_clean:${s.id}:batch-v7-planned:${batch.context.batchIndex}`
                const savedBatchState = readRuntimeTaskState(get().taskJournal, get().taskRecords, batchTaskId)
                const savedBatch = savedBatchState.journal
                if (
                  savedBatchState.task?.executionStatus === 'SUCCEEDED' &&
                  savedBatchState.task.resultStatus === 'VALID' &&
                  savedBatch?.output?.trim()
                ) {
                  batchOutputs[batchPosition] = savedBatch.output
""",
    'clean batch canonical read'
)
text = replace_once(
    text,
    """      const savedTaskId = `${sessionId}:module:v2:${module.key}`
      const saved = get().taskJournal[savedTaskId]
      const outsideTargetedRetry = get().moduleRetryScope.length > 0 && !get().moduleRetryScope.includes(module.key)
""",
    """      const savedTaskId = `${sessionId}:module:v2:${module.key}`
      const savedState = readRuntimeTaskState(get().taskJournal, get().taskRecords, savedTaskId)
      const saved = savedState.journal
      const savedTask = savedState.task
      const outsideTargetedRetry = get().moduleRetryScope.length > 0 && !get().moduleRetryScope.includes(module.key)
""",
    'module canonical read setup'
)
text = replace_once(
    text,
    """      const inputFingerprint = fingerprintModuleMessages(messages, 'v2')
      const reusableInput = outsideTargetedRetry || saved?.inputFingerprint === inputFingerprint
      if (reusableInput && saved?.output?.trim() && isNoAnalysisOutput(saved.output)) {
        const output = normalizeNoAnalysisOutput(saved.output)
        updateModuleState(module.key, { status: 'skipped', message: output, updatedAt: saved.updatedAt })
        return
      }
      if (reusableInput && saved?.status === 'complete' && saved.output?.trim()) {
        const output = module.key === 'material-review'
            ? normalizeMaterialReviewOutput(saved.output)
            : saved.output
        set((state) => ({ artifacts: { ...state.artifacts, [module.id]: output } }))
        updateModuleState(module.key, { status: 'done', updatedAt: saved.updatedAt })
        return
      }
""",
    """      const inputFingerprint = fingerprintModuleMessages(messages, 'v2')
      const reusableInput = outsideTargetedRetry || savedTask?.inputFingerprint === inputFingerprint
      if (
        reusableInput && saved?.output?.trim() &&
        savedTask?.executionStatus === 'SUCCEEDED' &&
        (savedTask.resultStatus === 'INSUFFICIENT' || isNoAnalysisOutput(saved.output))
      ) {
        const output = normalizeNoAnalysisOutput(saved.output)
        updateModuleState(module.key, { status: 'skipped', message: output, updatedAt: saved.updatedAt })
        return
      }
      if (
        reusableInput && saved?.output?.trim() &&
        savedTask?.executionStatus === 'SUCCEEDED' && savedTask.resultStatus === 'VALID'
      ) {
        const output = module.key === 'material-review'
            ? normalizeMaterialReviewOutput(saved.output)
            : saved.output
        set((state) => ({ artifacts: { ...state.artifacts, [module.id]: output } }))
        updateModuleState(module.key, { status: 'done', updatedAt: saved.updatedAt })
        return
      }
""",
    'module canonical reuse decisions'
)
path.write_text(text, encoding='utf-8')
