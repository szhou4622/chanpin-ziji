import { describe, expect, it } from 'vitest'
import { REPORT_MODULES_V2, type ModuleRunState, type ReportModule } from '../../shared/types'
import {
  buildModuleExecutionBatches,
  collectAffectedModuleKeys,
  moduleDependenciesSettled
} from './moduleDependencyResolver'

describe('module dependency resolver', () => {
  it('derives the active v2 execution batches from dependsOn', () => {
    const batches = buildModuleExecutionBatches(REPORT_MODULES_V2)
    expect(batches.map((batch) => batch.map((module) => module.id))).toEqual([
      [1, 2, 3, 5],
      [4],
      [6]
    ])
  })

  it('computes downstream retry closure without hard-coded module ids', () => {
    expect([...collectAffectedModuleKeys(REPORT_MODULES_V2, ['selling-points'])]).toEqual([
      'selling-points',
      'audience-sp-scene'
    ])
    expect([...collectAffectedModuleKeys(REPORT_MODULES_V2, ['material-review'])]).toEqual([
      'material-review',
      'selling-points',
      'audience-sp-scene'
    ])
    expect([...collectAffectedModuleKeys(REPORT_MODULES_V2, ['voc'])]).toEqual([
      'voc',
      'audience-sp-scene'
    ])
  })

  it('treats failed or skipped upstream modules as settled ordering dependencies', () => {
    const m4 = REPORT_MODULES_V2.find((module) => module.key === 'selling-points')!
    const done = (status: ModuleRunState['status']): ModuleRunState => ({
      status,
      updatedAt: '2026-08-30T08:00:00.000Z'
    })
    expect(moduleDependenciesSettled(m4, {
      'product-info': done('done'),
      'material-review': done('skipped')
    })).toBe(true)
    expect(moduleDependenciesSettled(m4, {
      'product-info': done('failed'),
      'material-review': done('done')
    })).toBe(true)
    expect(moduleDependenciesSettled(m4, {
      'product-info': done('running'),
      'material-review': done('done')
    })).toBe(false)
  })

  it('rejects missing dependencies and dependency cycles instead of silently deadlocking', () => {
    const missing: ReportModule[] = [
      { ...REPORT_MODULES_V2[0], key: 'product-info', dependsOn: ['benchmark-brands'] }
    ]
    expect(() => buildModuleExecutionBatches(missing)).toThrow(/依赖不存在/u)

    const cycle: ReportModule[] = [
      { ...REPORT_MODULES_V2[0], key: 'product-info', dependsOn: ['material-review'] },
      { ...REPORT_MODULES_V2[2], key: 'material-review', dependsOn: ['product-info'] }
    ]
    expect(() => buildModuleExecutionBatches(cycle)).toThrow(/存在循环/u)
  })
})
