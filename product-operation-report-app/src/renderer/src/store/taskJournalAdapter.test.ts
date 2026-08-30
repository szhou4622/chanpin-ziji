import { describe, expect, it } from 'vitest'
import type { ProjectTaskSnapshot } from '../../../shared/types'
import { removeTaskJournalEntries, writeTaskJournalEntry } from './taskJournalAdapter'

describe('task journal compatibility adapter', () => {
  it('writes immutably and injects one canonical timestamp', () => {
    const original: Record<string, ProjectTaskSnapshot> = {
      old: { kind: 'module', status: 'complete', updatedAt: '2026-08-20T00:00:00.000Z' }
    }
    const next = writeTaskJournalEntry(
      original,
      'module:m5',
      { kind: 'module', status: 'failed', output: 'partial', inputFingerprint: 'fp-1' },
      () => '2026-08-30T06:30:00.000Z'
    )

    expect(next).not.toBe(original)
    expect(original['module:m5']).toBeUndefined()
    expect(next['module:m5']).toEqual({
      kind: 'module',
      status: 'failed',
      output: 'partial',
      inputFingerprint: 'fp-1',
      updatedAt: '2026-08-30T06:30:00.000Z'
    })
    expect(next.old).toBe(original.old)
  })

  it('preserves an explicit migration/recovery timestamp', () => {
    const next = writeTaskJournalEntry(
      {},
      'source:a',
      {
        kind: 'source_clean',
        status: 'complete',
        updatedAt: '2026-08-20T03:00:00.000Z'
      },
      () => 'SHOULD_NOT_BE_USED'
    )
    expect(next['source:a'].updatedAt).toBe('2026-08-20T03:00:00.000Z')
  })

  it('removes only selected tasks without mutating the source journal', () => {
    const journal: Record<string, ProjectTaskSnapshot> = {
      'session:module:v2:voc': { kind: 'module', status: 'complete', updatedAt: '2026-08-20T00:00:00.000Z' },
      'session:module:v2:product-info': { kind: 'module', status: 'complete', updatedAt: '2026-08-20T00:00:01.000Z' },
      'session:source_clean:a': { kind: 'source_clean', status: 'complete', updatedAt: '2026-08-20T00:00:02.000Z' }
    }
    const next = removeTaskJournalEntries(journal, (taskId) => taskId.includes(':module:v2:voc'))

    expect(Object.keys(next)).toEqual([
      'session:module:v2:product-info',
      'session:source_clean:a'
    ])
    expect(journal['session:module:v2:voc']).toBeDefined()
  })
})
