import { describe, expect, it } from 'vitest'
import { buildProjectSnapshot, type ProjectSnapshotState } from './persistence'

function baseState(overrides: Partial<ProjectSnapshotState> = {}): ProjectSnapshotState {
  return {
    projectRevision: 3,
    analysisSessionId: 'session-a',
    sources: [],
    messages: [],
    cleanedData: '',
    cleanDetails: [],
    artifacts: {},
    taskJournal: {},
    taskRecords: {},
    currentTaskByLogicalKey: {},
    reportMarkdown: '',
    reportStale: false,
    phase: 'idle',
    steering: '',
    engineVersion: 'v2',
    readOnly: false,
    legacyNotice: '',
    moduleStates: {},
    ...overrides
  }
}

describe('project snapshot current task bridge', () => {
  it('persists the explicit current task pointer without inferring another task', () => {
    const snapshot = buildProjectSnapshot(baseState({
      currentTaskByLogicalKey: {
        'session:module:v2:voc': 'session:module:v2:voc@run-b'
      }
    }))

    expect(snapshot.currentTaskByLogicalKey).toEqual({
      'session:module:v2:voc': 'session:module:v2:voc@run-b'
    })
  })

  it('writes an empty index for legacy renderer state that has no pointer map', () => {
    const state = baseState()
    delete state.currentTaskByLogicalKey
    expect(buildProjectSnapshot(state).currentTaskByLogicalKey).toEqual({})
  })
})
