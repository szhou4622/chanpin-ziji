export interface AbortGroup {
  createRegistrar: () => (fn: (() => void) | null) => void
  abortAll: () => void
  isAborted: () => boolean
  activeCount: () => number
}

/**
 * Groups multiple independently changing abort handles under one parent cancellation action.
 * Each registrar owns exactly one current child handle, so one request clearing its handle does
 * not erase siblings that are still running.
 */
export function createAbortGroup(): AbortGroup {
  const active = new Set<() => void>()
  let aborted = false

  const createRegistrar = (): ((fn: (() => void) | null) => void) => {
    let current: (() => void) | null = null
    return (next) => {
      if (current) active.delete(current)
      current = next
      if (!next) return
      if (aborted) {
        next()
        if (current === next) current = null
        return
      }
      active.add(next)
    }
  }

  const abortAll = (): void => {
    if (aborted) return
    aborted = true
    const pending = [...active]
    active.clear()
    for (const abort of pending) abort()
  }

  return {
    createRegistrar,
    abortAll,
    isAborted: () => aborted,
    activeCount: () => active.size
  }
}
