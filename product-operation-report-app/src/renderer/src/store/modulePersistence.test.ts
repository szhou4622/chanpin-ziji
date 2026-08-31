import { describe, expect, it, vi } from 'vitest'
import {
  completedModulePersistenceWarning,
  persistCompletedModuleSnapshot
} from './modulePersistence'

describe('completed module persistence boundary', () => {
  it('returns success when the project snapshot is saved', async () => {
    const save = vi.fn().mockResolvedValue(undefined)

    await expect(persistCompletedModuleSnapshot(save)).resolves.toEqual({ ok: true })
    expect(save).toHaveBeenCalledTimes(1)
  })

  it('contains a save failure instead of rejecting the completed module execution', async () => {
    const error = new Error('disk full')
    const save = vi.fn().mockRejectedValue(error)

    const result = await persistCompletedModuleSnapshot(save)

    expect(result).toEqual({ ok: false, error })
    expect(save).toHaveBeenCalledTimes(1)
  })

  it('warns that the in-memory result is retained and later full snapshots can retry', () => {
    const warning = completedModulePersistenceWarning('M2 成交人群分析', '磁盘空间不足')

    expect(warning).toContain('M2 成交人群分析 已完成')
    expect(warning).toContain('本地自动保存失败')
    expect(warning).toContain('结果仍保留在当前窗口')
    expect(warning).toContain('后续模块或最终报告保存时会再次写入完整项目快照')
    expect(warning).toContain('请暂时不要关闭软件')
  })
})
