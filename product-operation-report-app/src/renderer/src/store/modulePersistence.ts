export interface ModulePersistenceResult {
  ok: boolean
  error?: unknown
}

/**
 * Persistence happens after a module business outcome has already been committed in memory.
 * A storage failure must therefore be reported separately instead of being reclassified as
 * a module execution failure by the outer Promise.allSettled boundary.
 */
export async function persistCompletedModuleSnapshot(
  save: () => Promise<unknown>
): Promise<ModulePersistenceResult> {
  try {
    await save()
    return { ok: true }
  } catch (error) {
    return { ok: false, error }
  }
}

export function completedModulePersistenceWarning(
  moduleLabel: string,
  errorText: string
): string {
  return `${moduleLabel} 已完成，但这次本地自动保存失败：${errorText}。结果仍保留在当前窗口；后续模块或最终报告保存时会再次写入完整项目快照，请暂时不要关闭软件。`
}
