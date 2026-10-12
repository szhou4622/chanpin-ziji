import { afterEach, describe, expect, it, vi } from 'vitest'
import { MANAGED_MODEL } from '../shared/modelConfig'
import { getManagedModelState } from './managedModel'
import { profilesForTask } from './modelFallback'

vi.mock('electron', () => ({ app: { isPackaged: true }, safeStorage: {} }))

afterEach(() => vi.unstubAllEnvs())

describe('packaged Ark routing', () => {
  it('routes cleaning and every module to Doubao without exposing a provider key', () => {
    vi.stubEnv('PRODUCT_REPORT_MANAGED_MODEL_CONFIG_JSON', JSON.stringify({
      model: 'old-model', apiKey: 'must-not-reach-client'
    }))
    const state = getManagedModelState()
    expect(state.mode).toBe('proxy')
    expect(state.profiles.map((profile) => profile.model)).toEqual([MANAGED_MODEL])
    expect(state.profile?.baseURL).toBe('https://api.dadaozixun.com/api/product-operation-report/v1')
    expect(JSON.stringify(state)).not.toContain('must-not-reach-client')
    for (const taskType of [
      'source_clean', 'summary', 'analysis_step', 'final_part', 'revision_part',
      'module_product_info', 'module_platform_audience', 'module_material_review',
      'module_benchmark', 'module_selling_points', 'module_voc', 'module_ranking',
      'module_audience_sp_scene'
    ] as const) {
      expect(profilesForTask(state.profiles, taskType).map((profile) => profile.model)).toEqual([MANAGED_MODEL])
    }
  })
})
