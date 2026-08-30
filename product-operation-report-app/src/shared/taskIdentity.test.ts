import { describe, expect, it } from 'vitest'
import {
  buildTaskInstanceId,
  resolvedTaskLogicalKey,
  taskBelongsToLogicalKey
} from './taskIdentity'

describe('task identity boundary', () => {
  it('separates a stable logical slot from immutable task instances', () => {
    const logicalKey = 'session:module:v2:voc'
    const first = buildTaskInstanceId(logicalKey, 'run-a')
    const second = buildTaskInstanceId(logicalKey, 'run-b')

    expect(first).toBe('session:module:v2:voc@run-a')
    expect(second).toBe('session:module:v2:voc@run-b')
    expect(first).not.toBe(second)
    expect(resolvedTaskLogicalKey({ id: first, logicalKey })).toBe(logicalKey)
    expect(taskBelongsToLogicalKey({ id: second, logicalKey }, logicalKey)).toBe(true)
  })

  it('treats legacy ids as their own logical key when no explicit logicalKey exists', () => {
    expect(resolvedTaskLogicalKey({ id: 'session:module:v2:voc' })).toBe('session:module:v2:voc')
    expect(taskBelongsToLogicalKey({ id: 'session:module:v2:voc' }, 'session:module:v2:voc')).toBe(true)
  })

  it('fails closed on malformed or oversized instance identity', () => {
    expect(() => buildTaskInstanceId('bad key with spaces', 'run-a')).toThrow(/logicalKey/u)
    expect(() => buildTaskInstanceId('session:module:v2:voc', 'bad token with spaces')).toThrow(/instanceToken/u)
    expect(() => buildTaskInstanceId(`slot:${'a'.repeat(290)}`, 'run-a')).toThrow(/过长|格式无效/u)
  })
})
