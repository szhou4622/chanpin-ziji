import { REPORT_MODULES_V2 } from './types'

/**
 * Product-facing rules for the active v2 engine.
 *
 * Keep this file small and stable: UI/main/renderer may read these values,
 * while parser/provider hard safety limits remain owned by their subsystems.
 */
export const PRODUCT_POLICY = {
  analysis: {
    activeEngine: 'v2' as const,
    modules: REPORT_MODULES_V2
  },
  upload: {
    maxTopLevelFiles: 50,
    maxTotalBytes: 350 * 1024 * 1024,
    maxRegularFileBytes: 40 * 1024 * 1024,
    maxImageBytes: 25 * 1024 * 1024,
    maxZipBytes: 120 * 1024 * 1024
  },
  sourceMetadata: {
    attributionRequired: true,
    kindRequired: true,
    platformRequired: false,
    noteRequired: false
  },
  runtime: {
    parseConcurrency: 2,
    aiConcurrency: 4,
    visionConcurrency: 2
  }
} as const

export type ProductPolicy = typeof PRODUCT_POLICY
