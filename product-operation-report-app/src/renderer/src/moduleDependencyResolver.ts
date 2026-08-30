import type { ModuleKey, ModuleRunState, ReportModule } from '../../shared/types'

const TERMINAL_MODULE_STATUSES = new Set<ModuleRunState['status']>(['done', 'failed', 'skipped'])

function validateModuleGraph(modules: readonly ReportModule[]): Map<ModuleKey, ReportModule> {
  const byKey = new Map<ModuleKey, ReportModule>()
  const ids = new Set<number>()
  for (const module of modules) {
    if (byKey.has(module.key)) throw new Error(`模块依赖图包含重复 key：${module.key}`)
    if (ids.has(module.id)) throw new Error(`模块依赖图包含重复 id：M${module.id}`)
    byKey.set(module.key, module)
    ids.add(module.id)
  }
  for (const module of modules) {
    for (const dependency of module.dependsOn) {
      if (dependency === module.key) throw new Error(`模块 ${module.key} 不能依赖自身`)
      if (!byKey.has(dependency)) {
        throw new Error(`模块 ${module.key} 依赖不存在的模块：${dependency}`)
      }
    }
  }
  return byKey
}

/**
 * Derives deterministic parallel execution batches from dependsOn only.
 * A batch is a barrier: the next batch starts after every module in the current
 * batch has reached a terminal outcome, matching the existing v2 runtime semantics.
 */
export function buildModuleExecutionBatches(modules: readonly ReportModule[]): ReportModule[][] {
  validateModuleGraph(modules)
  const remaining = new Set(modules.map((module) => module.key))
  const completed = new Set<ModuleKey>()
  const batches: ReportModule[][] = []

  while (remaining.size > 0) {
    const batch = modules.filter((module) =>
      remaining.has(module.key) && module.dependsOn.every((dependency) => completed.has(dependency))
    )
    if (!batch.length) {
      throw new Error(`模块依赖图存在循环，无法继续调度：${[...remaining].join('、')}`)
    }
    batches.push(batch)
    for (const module of batch) {
      remaining.delete(module.key)
      completed.add(module.key)
    }
  }

  return batches
}

/** Downstream invalidation/retry closure, including every seed module itself. */
export function collectAffectedModuleKeys(
  modules: readonly ReportModule[],
  seeds: Iterable<ModuleKey>
): Set<ModuleKey> {
  const byKey = validateModuleGraph(modules)
  const affected = new Set<ModuleKey>()
  for (const seed of seeds) {
    if (!byKey.has(seed)) throw new Error(`无法计算下游：模块不存在 ${seed}`)
    affected.add(seed)
  }

  let changed = true
  while (changed) {
    changed = false
    for (const module of modules) {
      if (affected.has(module.key)) continue
      if (!module.dependsOn.some((dependency) => affected.has(dependency))) continue
      affected.add(module.key)
      changed = true
    }
  }
  return affected
}

/**
 * Dependency means ordering, not success. A failed/skipped upstream is settled and
 * the downstream module may still run with explicit missing-dependency context.
 */
export function moduleDependenciesSettled(
  module: ReportModule,
  states: Partial<Record<ModuleKey, ModuleRunState>>
): boolean {
  return module.dependsOn.every((dependency) => {
    const status = states[dependency]?.status
    return Boolean(status && TERMINAL_MODULE_STATUSES.has(status))
  })
}
