import { describe, expect, it, vi } from 'vitest'
import { createAbortGroup } from './abortGroup'

describe('abort group', () => {
  it('keeps sibling abort handles when one request clears its own handle', () => {
    const group = createAbortGroup()
    const setA = group.createRegistrar()
    const setB = group.createRegistrar()
    const abortA = vi.fn()
    const abortB = vi.fn()

    setA(abortA)
    setB(abortB)
    expect(group.activeCount()).toBe(2)

    setA(null)
    expect(group.activeCount()).toBe(1)

    group.abortAll()
    expect(abortA).not.toHaveBeenCalled()
    expect(abortB).toHaveBeenCalledTimes(1)
  })

  it('broadcasts one parent abort to all current concurrent requests', () => {
    const group = createAbortGroup()
    const aborts = [vi.fn(), vi.fn(), vi.fn(), vi.fn()]

    aborts.forEach((abort) => group.createRegistrar()(abort))
    expect(group.activeCount()).toBe(4)

    group.abortAll()

    aborts.forEach((abort) => expect(abort).toHaveBeenCalledTimes(1))
    expect(group.isAborted()).toBe(true)
    expect(group.activeCount()).toBe(0)
  })

  it('immediately aborts a child registered after parent cancellation', () => {
    const group = createAbortGroup()
    group.abortAll()

    const lateAbort = vi.fn()
    group.createRegistrar()(lateAbort)

    expect(lateAbort).toHaveBeenCalledTimes(1)
    expect(group.activeCount()).toBe(0)
  })

  it('is idempotent when the parent abort is invoked repeatedly', () => {
    const group = createAbortGroup()
    const abort = vi.fn()
    group.createRegistrar()(abort)

    group.abortAll()
    group.abortAll()

    expect(abort).toHaveBeenCalledTimes(1)
  })

  it('replaces one registrar handle without retaining the old retry-stage handle', () => {
    const group = createAbortGroup()
    const setAbort = group.createRegistrar()
    const first = vi.fn()
    const retryDelay = vi.fn()

    setAbort(first)
    setAbort(null)
    setAbort(retryDelay)

    expect(group.activeCount()).toBe(1)
    group.abortAll()
    expect(first).not.toHaveBeenCalled()
    expect(retryDelay).toHaveBeenCalledTimes(1)
  })
})
