import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { PRODUCT_POLICY } from './productPolicy'
import { REPORT_MODULES, REPORT_MODULES_V2 } from './types'

const ACTIVE_PROMPT_MAPPING = {
  'product-info': 'M1-product-info.md',
  'platform-audience': 'M2-audience-analysis.md',
  'material-review': 'M3-material-review.md',
  'selling-points': 'M4-selling-point-strategy.md',
  voc: 'M5-voc.md',
  'audience-sp-scene': 'M6-audience-sp-scene.md'
} as const

describe('active architecture guard', () => {
  it('keeps v2 as the only active report engine', () => {
    expect(PRODUCT_POLICY.analysis.activeEngine).toBe('v2')
    expect(REPORT_MODULES).toBe(REPORT_MODULES_V2)
    expect(PRODUCT_POLICY.analysis.modules).toBe(REPORT_MODULES_V2)
  })

  it('keeps exactly the active M1-M6 DAG and excludes legacy modules', () => {
    const active = [...REPORT_MODULES_V2].sort((left, right) => left.id - right.id)
    expect(active.map((module) => module.id)).toEqual([1, 2, 3, 4, 5, 6])
    expect(active.map((module) => module.key)).toEqual([
      'product-info',
      'platform-audience',
      'material-review',
      'selling-points',
      'voc',
      'audience-sp-scene'
    ])
    expect(REPORT_MODULES_V2.find((module) => module.key === 'selling-points')?.dependsOn).toEqual([
      'product-info',
      'material-review'
    ])
    expect(REPORT_MODULES_V2.find((module) => module.key === 'audience-sp-scene')?.dependsOn).toEqual([
      'platform-audience',
      'selling-points',
      'voc'
    ])
    expect(REPORT_MODULES_V2.some((module) => module.key === 'benchmark-brands')).toBe(false)
    expect(REPORT_MODULES_V2.some((module) => module.key === 'selling-point-ranking')).toBe(false)
    expect(REPORT_MODULES_V2.every((module) => module.needsWebSearch === false)).toBe(true)
  })

  it('locks active module prompt mapping away from legacy prompt files', () => {
    for (const module of REPORT_MODULES_V2) {
      expect(module.promptFile).toBe(ACTIVE_PROMPT_MAPPING[module.key as keyof typeof ACTIVE_PROMPT_MAPPING])
    }
  })

  it('locks current product-facing upload, metadata and concurrency policy', () => {
    expect(PRODUCT_POLICY.upload).toEqual({
      maxTopLevelFiles: 50,
      maxTotalBytes: 350 * 1024 * 1024,
      maxRegularFileBytes: 40 * 1024 * 1024,
      maxImageBytes: 25 * 1024 * 1024,
      maxZipBytes: 120 * 1024 * 1024
    })
    expect(PRODUCT_POLICY.sourceMetadata).toEqual({
      attributionRequired: true,
      kindRequired: true,
      platformRequired: false,
      noteRequired: false
    })
    expect(PRODUCT_POLICY.runtime).toEqual({
      parseConcurrency: 2,
      aiConcurrency: 4,
      visionConcurrency: 2
    })
  })

  it('keeps npm and package-lock as the only production package-manager path', () => {
    const packageJson = JSON.parse(readFileSync(join(process.cwd(), 'package.json'), 'utf8')) as { packageManager?: string }
    expect(packageJson.packageManager).toMatch(/^npm@/u)
    expect(existsSync(join(process.cwd(), 'package-lock.json'))).toBe(true)
    expect(existsSync(join(process.cwd(), 'pnpm-lock.yaml'))).toBe(false)
    expect(existsSync(join(process.cwd(), 'pnpm-workspace.yaml'))).toBe(false)
  })
})
