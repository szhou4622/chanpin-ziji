import { describe, expect, it, vi } from 'vitest'
import type { ModelProfile } from '../shared/types'
import { profileForFallbackAttempt, shouldTryModelFallback } from './modelFallback'

describe('task-scoped model fallback', () => {
  it('refreshes a proxy session before the fallback, without changing the primary profile', async () => {
    const profile: ModelProfile = {
      id: 'backup', name: 'backup', baseURL: 'https://example.invalid/v1',
      apiKey: 'old-session', model: 'gpt-5.5', supportsVision: false
    }
    const refresh = vi.fn(() => Promise.resolve('fresh-session'))
    expect(await profileForFallbackAttempt(profile, 0, refresh)).toBe(profile)
    expect(refresh).not.toHaveBeenCalled()
    const backup = await profileForFallbackAttempt(profile, 1, refresh)
    expect(backup.apiKey).toBe('fresh-session')
    expect(profile.apiKey).toBe('old-session')
    expect(refresh).toHaveBeenCalledOnce()
  })
  it('allows zero-output provider recovery for cleaning and every report module', () => {
    expect(shouldTryModelFallback({
      taskType: 'source_clean',
      failureKind: 'provider_error',
      outputChars: 0,
      aborted: false,
      hasNext: true
    })).toBe(true)
    expect(shouldTryModelFallback({
      taskType: 'module_platform_audience',
      failureKind: 'provider_error',
      outputChars: 0,
      aborted: false,
      hasNext: true
    })).toBe(true)
    expect(shouldTryModelFallback({
      taskType: 'module_audience_sp_scene',
      failureKind: 'provider_error',
      outputChars: 0,
      aborted: false,
      hasNext: true
    })).toBe(true)
    for (const taskType of [
      'module_product_info',
      'module_material_review',
      'module_selling_points',
      'module_voc'
    ] as const) {
      expect(shouldTryModelFallback({
        taskType,
        failureKind: 'provider_error',
        outputChars: 0,
        aborted: false,
        hasNext: true
      })).toBe(true)
    }
    expect(shouldTryModelFallback({
      taskType: 'final_part',
      failureKind: 'provider_error',
      outputChars: 0,
      aborted: false,
      hasNext: true
    })).toBe(false)
  })

  it('never switches after partial output, user stop, or a security rejection', () => {
    expect(shouldTryModelFallback({
      taskType: 'module_platform_audience',
      failureKind: 'provider_error',
      outputChars: 8,
      aborted: false,
      hasNext: true
    })).toBe(false)
    expect(shouldTryModelFallback({
      taskType: 'module_platform_audience',
      failureKind: 'provider_error',
      outputChars: 0,
      aborted: true,
      hasNext: true
    })).toBe(false)
    expect(shouldTryModelFallback({
      taskType: 'module_platform_audience',
      failureKind: 'safety',
      outputChars: 0,
      aborted: false,
      hasNext: true
    })).toBe(false)
  })
})
