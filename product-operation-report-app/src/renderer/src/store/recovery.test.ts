import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createHash } from 'node:crypto'
import type { ChatMessage, ModelTaskContext, ModuleKey, SavedProject } from '../../../shared/types'
import { buildProjectSnapshot, useStore } from '../store'

const productOutput = [
  '1. 产品基础', '2. SKU规格', '3. 价格', '4. 优惠赠品', '5. 原料/成分/材质',
  '6. 工艺技术', '7. 产品属性与功能', '8. 品牌背书', '9. 产品背书'
].map((label) => `${label}\n信息：已提供的产品事实\n来源：产品手卡`).join('\n\n')
const productDigest = createHash('sha256').update(productOutput).digest('hex')
const taskId = 'recover-report:module:v2:product-info'
const prompt = (key: ModuleKey) => ({ key, systemPrompt: 'test', outputTemplate: '', validation: '', inputDescription: '', purpose: '' })
type Handlers = Parameters<typeof window.api.sendChat>[2]

beforeEach(() => {
  useStore.setState(useStore.getInitialState(), true)
  useStore.setState({
    analysisSessionId: 'recover-report', phase: 'checkpoint1', cleanedData: '产品清洗资料',
    sources: [{ id: 'product', name: '产品手卡.md', kind: 'doc', kindV1: 'product-supply', text: '产品事实', attribution: '自有数据' }],
    cleanDetails: [{ id: 'product', name: '产品手卡.md', text: '产品事实' }]
  })
})

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

function installBillingBridge() {
  let persisted: SavedProject | undefined
  let firstConfirmation = true
  const chargedAttempts = new Set<string>()
  const modelCalls: ModelTaskContext[] = []
  const confirm = vi.fn((receipt: { requestId: string; logicalTaskId: string }) => {
    const task = persisted?.taskJournal?.[taskId]
    expect(task?.status).toBe('complete')
    expect(task?.output).toBe(productOutput)
    expect(task?.billingAttemptId).toBe(receipt.requestId)
    expect(receipt.logicalTaskId).toBe(taskId)
    chargedAttempts.add(receipt.requestId)
    if (firstConfirmation) {
      firstConfirmation = false
      return Promise.reject(new Error('服务器已扣费，但确认响应超时'))
    }
    return Promise.resolve({ state: 'charged', chargedUnits: 7_000_000 })
  })
  const api = {
    getModulePrompt: (key: ModuleKey) => Promise.resolve(prompt(key)),
    saveLastProject: (project: SavedProject) => { persisted = structuredClone(project); return Promise.resolve(project) },
    confirmSavedModelResult: confirm,
    rejectModelResult: vi.fn(() => Promise.resolve()),
    storeReportResultCache: () => Promise.resolve(),
    getSettings: () => Promise.resolve({ profiles: [] }),
    getSopRules: () => Promise.resolve(''),
    loadLastProject: () => Promise.resolve(persisted),
    loadPreviousProject: () => Promise.resolve(null),
    sendChat: (_messages: ChatMessage[], context: ModelTaskContext, handlers: Handlers) => {
      modelCalls.push(context)
      queueMicrotask(() => context.taskType === 'module_product_info'
        ? handlers.onDone?.(productOutput, 'attempt-product', productDigest)
        : handlers.onDone?.('暂无分析：缺少可用证据。'))
      return { abort: () => undefined }
    }
  }
  vi.stubGlobal('window', { setTimeout, clearTimeout, api })
  return { api, confirm, modelCalls, chargedAttempts, persisted: () => persisted }
}

describe('saved result confirmation recovery', () => {
  it.each([false, true])('keeps only usable prior output when an explicit redo returns no analysis (invalidated=%s)', async (outputInvalidated) => {
    const bridge = installBillingBridge()
    const saved = {
      kind: 'module' as const, status: 'complete' as const, output: productOutput,
      billingAttemptId: 'attempt-original-paid', billingLogicalTaskId: taskId,
      billingOutputSha256: productDigest, billingConfirmed: true, outputInvalidated,
      updatedAt: '2026-10-12T10:00:00Z'
    }
    useStore.setState({
      phase: 'done', artifacts: { 1: productOutput }, reportMarkdown: productOutput,
      taskJournal: { [taskId]: saved },
      moduleStates: { 'product-info': { status: 'done', updatedAt: saved.updatedAt } }
    })
    bridge.api.sendChat = (_messages, context, handlers) => {
      bridge.modelCalls.push(context)
      const text = '暂无分析：本轮没有新的可用证据。'
      queueMicrotask(() => handlers.onDone?.(text, `empty-${context.taskType}`, createHash('sha256').update(text).digest('hex')))
      return { abort: () => undefined }
    }
    await useStore.getState().retryModule('product-info')
    const redo = bridge.modelCalls.find((context) => context.taskType === 'module_product_info')!
    expect(redo.manualRedoOf).toBe(taskId)
    expect(bridge.api.rejectModelResult).toHaveBeenCalledWith({ requestId: 'empty-module_product_info', logicalTaskId: redo.billingRequestId })
    expect(bridge.confirm).not.toHaveBeenCalled()
    expect(useStore.getState().taskJournal[taskId]).toEqual(saved)
    expect(useStore.getState().moduleStates['product-info']?.status).toBe(outputInvalidated ? 'skipped' : 'done')
    if (outputInvalidated) {
      expect(useStore.getState().artifacts[1]).toBeUndefined()
      expect(useStore.getState().reportMarkdown).not.toContain(productOutput)
      expect(bridge.persisted()?.artifacts[1]).toBeUndefined()
    } else {
      expect(useStore.getState().artifacts[1]).toBe(productOutput)
      expect(useStore.getState().reportMarkdown).toContain(productOutput)
      expect(bridge.persisted()?.artifacts[1]).toBe(productOutput)
      expect(bridge.persisted()?.reportMarkdown).toContain(productOutput)
    }
  })

  it('retries a saved cleaning batch receipt without sending the source to the model again', async () => {
    let persisted: SavedProject | undefined
    let failConfirmation = true
    const sendChat = vi.fn((messages: ChatMessage[], _context: ModelTaskContext, handlers: Handlers) => {
      const evidence = [...new Set(JSON.stringify(messages).match(/POR-[RTI]-[A-F0-9]{8}-\d{6}/gu) || [])]
      const output = `已提取的产品事实\n${evidence.join('\n')}`
      queueMicrotask(() => handlers.onDone?.(output, 'attempt-clean', createHash('sha256').update(output).digest('hex')))
      return { abort: () => undefined }
    })
    const confirm = vi.fn((receipt: { logicalTaskId: string; requestId: string }) => {
      expect(persisted?.taskJournal?.[receipt.logicalTaskId]).toMatchObject({ status: 'complete', billingAttemptId: receipt.requestId })
      if (failConfirmation) {
        failConfirmation = false
        return Promise.reject(new Error('confirmation reply lost'))
      }
      return Promise.resolve({ state: 'charged', chargedUnits: 1_000_000 })
    })
    vi.stubGlobal('window', { setTimeout, clearTimeout, api: {
      sendChat, confirmSavedModelResult: confirm,
      lookupSourceCleanCache: () => Promise.resolve({ hit: false }),
      storeSourceCleanCache: () => Promise.resolve({ stored: true }),
      recordCostOptimization: () => Promise.resolve(true),
      saveLastProject: (project: SavedProject) => { persisted = structuredClone(project); return Promise.resolve(project) }
    } })
    useStore.setState({ cleanDetails: [], cleanedData: '', phase: 'idle' })
    await useStore.getState()._runCleaning(false)
    const saved = Object.values(useStore.getState().taskJournal).find((task) => task.billingAttemptId === 'attempt-clean')
    expect(saved?.status).toBe('complete')
    expect(useStore.getState().cleanDetails).toHaveLength(0)
    await useStore.getState()._runCleaning(false)
    expect(sendChat).toHaveBeenCalledTimes(1)
    expect(confirm).toHaveBeenCalledTimes(2)
    expect(useStore.getState().cleanDetails).toHaveLength(1)
    expect(useStore.getState().phase).toBe('checkpoint1')
    expect(Object.values(useStore.getState().taskJournal).find((task) => task.billingAttemptId === 'attempt-clean')?.billingConfirmed).toBe(true)
  })

  it('keeps completed output and proof after a lost confirmation response and retries only the receipt', async () => {
    const bridge = installBillingBridge()
    await useStore.getState()._runAnalysis()
    const retained = useStore.getState().taskJournal[taskId]
    expect(retained).toMatchObject({ status: 'complete', output: productOutput, billingAttemptId: 'attempt-product', billingOutputSha256: productDigest })
    expect(useStore.getState().moduleStates['product-info']?.status).toBe('failed')
    expect(bridge.persisted()?.taskJournal?.[taskId]).toMatchObject(retained)

    // Retry instructions change the input fingerprint; this must still recover
    // the already generated result before any explicit new generation.
    await useStore.getState().retryModule('product-info', '重试 M1，重点核对来源')
    expect(bridge.modelCalls.filter((call) => call.taskType === 'module_product_info')).toHaveLength(1)
    expect(bridge.confirm).toHaveBeenCalledTimes(2)
    expect(bridge.chargedAttempts.size).toBe(1)
    expect(useStore.getState().taskJournal[taskId]).toMatchObject({ ...retained, billingConfirmed: true })
    expect(useStore.getState().artifacts[1]).toBe(productOutput)
    expect(useStore.getState().moduleStates['product-info']?.status).toBe('done')
  })

  it('restores a complete pending result and confirms it after restart without another model call', async () => {
    const bridge = installBillingBridge()
    await useStore.getState()._runAnalysis()
    useStore.setState(useStore.getInitialState(), true)
    await useStore.getState().init()
    expect(bridge.modelCalls.filter((call) => call.taskType === 'module_product_info')).toHaveLength(1)
    expect(bridge.confirm).toHaveBeenCalledTimes(2)
    expect(bridge.chargedAttempts.size).toBe(1)
    expect(useStore.getState().taskJournal[taskId]).toMatchObject({ status: 'complete', output: productOutput, billingConfirmed: true })
    expect(bridge.persisted()?.taskJournal?.[taskId]?.billingConfirmed).toBe(true)
  })

  it('retains the result when the first local save fails and confirms only after a successful retry save', async () => {
    const bridge = installBillingBridge()
    const save = bridge.api.saveLastProject
    let failFirstSave = true
    bridge.api.saveLastProject = (project) => {
      if (failFirstSave && project.taskJournal?.[taskId]?.status === 'complete') {
        failFirstSave = false
        return Promise.reject(new Error('磁盘暂时不可用'))
      }
      return save(project)
    }
    await useStore.getState()._runAnalysis()
    expect(bridge.confirm).not.toHaveBeenCalled()
    expect(useStore.getState().taskJournal[taskId]?.status).toBe('complete')
    await useStore.getState().retryModule('product-info')
    expect(bridge.confirm).toHaveBeenCalledTimes(1)
    expect(bridge.modelCalls.filter((call) => call.taskType === 'module_product_info')).toHaveLength(1)
    expect(useStore.getState().taskJournal[taskId]?.billingAttemptId).toBe('attempt-product')
  })

  it('does not regenerate when persisting a successful billing acknowledgement fails', async () => {
    const bridge = installBillingBridge()
    await useStore.getState()._runAnalysis()
    const save = bridge.api.saveLastProject
    let failReceiptSave = true
    bridge.api.saveLastProject = (project) => {
      if (failReceiptSave && project.taskJournal?.[taskId]?.billingConfirmed) {
        failReceiptSave = false
        return Promise.reject(new Error('receipt checkpoint save failed'))
      }
      return save(project)
    }
    await useStore.getState().retryModule('product-info')
    expect(useStore.getState().taskJournal[taskId]?.billingConfirmed).not.toBe(true)
    expect(useStore.getState().moduleStates['product-info']?.status).toBe('failed')
    await useStore.getState().retryModule('product-info')
    expect(bridge.modelCalls.filter((call) => call.taskType === 'module_product_info')).toHaveLength(1)
    expect(bridge.confirm).toHaveBeenCalledTimes(3)
    expect(bridge.chargedAttempts.size).toBe(1)
    expect(useStore.getState().taskJournal[taskId]?.billingConfirmed).toBe(true)
  })
})

describe('analysis stop button', () => {
  it('stops the active concurrent module after the first module completes, without starting the next wave', async () => {
    const bridge = installBillingBridge()
    const pending = new Map<string, Handlers>()
    const aborted: string[] = []
    bridge.api.sendChat = (_messages, context, handlers) => {
      bridge.modelCalls.push(context)
      pending.set(context.taskType, handlers)
      return { abort: () => { aborted.push(context.taskType) } }
    }
    useStore.setState((state) => ({
      sources: [...state.sources, { id: 'audience', name: '人群.csv', kind: 'table', kindV1: 'audience-data', text: '年龄,占比\n31-40,60%' }],
      cleanDetails: [...state.cleanDetails, { id: 'audience', name: '人群.csv', text: '人群证据' }]
    }))
    const run = useStore.getState()._runAnalysis()
    await vi.waitFor(() => expect(pending.size).toBe(2))
    pending.get('module_product_info')!.onDone?.(productOutput)
    await vi.waitFor(() => expect(useStore.getState().moduleStates['product-info']?.status).toBe('done'))
    useStore.getState().abort()
    await run
    expect(aborted).toEqual(['module_platform_audience'])
    expect(bridge.modelCalls).toHaveLength(2)
    expect(useStore.getState().moduleStates['platform-audience']?.status).toBe('failed')
    expect(useStore.getState().artifacts[1]).toBe(productOutput)
    expect(useStore.getState().abortFn).toBeNull()
    expect(useStore.getState().phase).toBe('checkpoint1')
  })

  it('does not start the model when stopped while its prompt is still loading', async () => {
    const bridge = installBillingBridge()
    let releasePrompt!: (value: ReturnType<typeof prompt>) => void
    bridge.api.getModulePrompt = () => new Promise((resolve) => { releasePrompt = resolve })
    const run = useStore.getState()._runAnalysis()
    await vi.waitFor(() => expect(releasePrompt).toBeTypeOf('function'))
    useStore.getState().abort()
    releasePrompt(prompt('product-info'))
    await run
    expect(bridge.modelCalls).toHaveLength(0)
    expect(useStore.getState().abortFn).toBeNull()
    expect(useStore.getState().phase).toBe('checkpoint1')
  })
})

describe('obsolete output receipt recovery', () => {
  const sellingId = 'recover-report:module:v2:selling-points'
  const sellingOutput = [
    '品质需求\n安装方便', '价格需求\n无', '健康需求\n无', '情感需求\n无',
    '核心卖点总排序', 'TOP1｜安装方便', '需求类型：品质需求', '买点：节省时间',
    '自营依据：产品结构说明', '竞品依据：无', '卖点状态：待验证卖点',
    '排序判断：可用产品事实', '自营来源：旧产品手卡', '竞品来源：无'
  ].join('\n')
  const originalDigest = createHash('sha256').update(sellingOutput).digest('hex')

  async function prepareStaleProject(bridge: ReturnType<typeof installBillingBridge>) {
    useStore.setState({
      artifacts: { 1: productOutput, 4: sellingOutput },
      moduleStates: {
        'product-info': { status: 'done', updatedAt: '2026-10-12T10:00:00Z' },
        'selling-points': { status: 'done', updatedAt: '2026-10-12T09:00:00Z' }
      },
      taskJournal: { [sellingId]: {
        kind: 'module', status: 'complete', output: sellingOutput, updatedAt: '2026-10-12T09:00:00Z',
        billingAttemptId: 'old-attempt', billingOutputSha256: originalDigest,
        billingLogicalTaskId: 'old-logical'
      } }
    })
    await bridge.api.saveLastProject(buildProjectSnapshot(useStore.getState()))
    useStore.setState(useStore.getInitialState(), true)
  }

  it('keeps a stale result only as a receipt record across repeated restores', async () => {
    const bridge = installBillingBridge()
    bridge.api.confirmSavedModelResult = vi.fn(() => Promise.reject(new Error('receipt still unavailable')))
    await prepareStaleProject(bridge)
    await useStore.getState().init()
    expect(useStore.getState().taskJournal[sellingId]).toMatchObject({
      status: 'complete', output: sellingOutput, outputInvalidated: true,
      billingAttemptId: 'old-attempt', billingOutputSha256: originalDigest
    })
    expect(useStore.getState().artifacts[4]).toBeUndefined()
    expect(useStore.getState().moduleStates['selling-points']?.status).toBe('failed')
    useStore.setState(useStore.getInitialState(), true)
    await useStore.getState().init()
    expect(useStore.getState().artifacts[4]).toBeUndefined()
    expect(useStore.getState().moduleStates['selling-points']?.status).toBe('failed')
    expect(useStore.getState().taskJournal[sellingId]?.outputInvalidated).toBe(true)
    expect(bridge.modelCalls).toHaveLength(0)
  })

  it('settles the original receipt before generating a linked replacement and never reuses obsolete output', async () => {
    const bridge = installBillingBridge()
    const receipts: string[] = []
    let failFirst = true
    bridge.api.confirmSavedModelResult = vi.fn((receipt) => {
      receipts.push(receipt.requestId)
      if (failFirst) { failFirst = false; return Promise.reject(new Error('receipt reply lost')) }
      return Promise.resolve({ state: 'charged', chargedUnits: 1_000_000 })
    })
    const nextOutput = sellingOutput.replace('旧产品手卡', '新产品手卡')
    bridge.api.sendChat = (_messages, context, handlers) => {
      expect(receipts).toEqual(['old-attempt', 'old-attempt'])
      expect(useStore.getState().artifacts[4]).toBeUndefined()
      bridge.modelCalls.push(context)
      queueMicrotask(() => handlers.onDone?.(nextOutput, 'new-attempt', createHash('sha256').update(nextOutput).digest('hex')))
      return { abort: () => undefined }
    }
    await prepareStaleProject(bridge)
    await useStore.getState().init()
    await useStore.getState().retryModule('selling-points')
    expect(bridge.modelCalls).toHaveLength(1)
    expect(bridge.modelCalls[0].manualRedoOf).toBe('old-logical')
    expect(bridge.modelCalls[0].billingRequestId).toMatch(/:redo:/u)
    expect(receipts).toEqual(['old-attempt', 'old-attempt', 'new-attempt'])
    expect(useStore.getState().artifacts[4]).toBe(nextOutput)
    expect(useStore.getState().taskJournal[sellingId]?.outputInvalidated).not.toBe(true)
  })
})

describe('changed business inputs keep historical billing receipts', () => {
  const mutations: Array<{ name: string; apply: (state: ReturnType<typeof useStore.getState>) => void | Promise<void> }> = [
    { name: 'note', apply: (state) => state.setSourceNote('product', '新的业务备注') },
    { name: 'attribution', apply: (state) => state.setSourceAttribution('product', '竞品数据') },
    { name: 'unconfirmed attribution', apply: (state) => state.setUnconfirmedAttribution('自有数据') },
    { name: 'platform', apply: (state) => state.setSourcePlatform('product', '视频号') },
    { name: 'purpose', apply: (state) => state.setSourcePurpose('product', '经营分析') },
    { name: 'source kind', apply: (state) => state.setSourceKindV1('product', 'business-data') },
    { name: 'product name', apply: (state) => state.setSourceProductName('product', '新产品') },
    { name: 'product selection', apply: (state) => state.setMaterialProductSelection(['新产品']) },
    { name: 'remove source', apply: (state) => state.removeSource('product') },
    { name: 'add source', apply: (state) => state.addSources([{
      name: '新增资料.md', size: 4, arrayBuffer: () => Promise.resolve(new ArrayBuffer(4))
    } as File]) }
  ]

  function seedPaidResult(confirmed: boolean) {
    const saved = {
      kind: 'module' as const, status: 'complete' as const, output: productOutput,
      billingAttemptId: 'attempt-product', billingLogicalTaskId: taskId,
      billingOutputSha256: productDigest, billingConfirmed: confirmed,
      updatedAt: '2026-10-12T10:00:00Z'
    }
    const abort = vi.fn(() => expect(useStore.getState().analysisSessionId).toBe('recover-report'))
    useStore.setState({
      artifacts: { 1: productOutput }, reportMarkdown: productOutput, abortFn: abort,
      moduleStates: { 'product-info': { status: 'done', updatedAt: saved.updatedAt } },
      taskJournal: {
        [taskId]: saved,
        'recover-report:failed-without-proof': { kind: 'module', status: 'failed', output: 'incomplete', updatedAt: saved.updatedAt }
      }
    })
    return { saved, abort }
  }

  it.each(mutations.flatMap((mutation) => [false, true].map((confirmed) => ({ ...mutation, confirmed }))))(
    'preserves the original proof and rotates the business session for $name (confirmed=$confirmed)', async ({ name, apply, confirmed }) => {
      const bridge = installBillingBridge()
      Object.assign(bridge.api, { parseFile: () => Promise.resolve({ ok: true, text: '新增事实' }) })
      const { saved, abort } = seedPaidResult(confirmed)
      if (name === 'unconfirmed attribution') useStore.setState((state) => ({ sources: state.sources.map((source) => ({ ...source, attribution: '' })) }))
      await apply(useStore.getState())
      const state = useStore.getState()
      expect(state.analysisSessionId).not.toBe('recover-report')
      expect(state.projectRevision).toBe(1)
      expect(abort).toHaveBeenCalledTimes(1)
      expect(state.abortFn).toBeNull()
      expect(state.taskJournal[taskId]).toEqual({ ...saved, outputInvalidated: true })
      expect(state.taskJournal['recover-report:failed-without-proof']).toBeUndefined()
      expect(state.artifacts[1]).toBeUndefined()
      expect(state.moduleStates).toEqual({})
      expect(state.reportStale).toBe(true)
      await bridge.api.saveLastProject(buildProjectSnapshot(state))
      expect(bridge.persisted()?.taskJournal?.[taskId]).toEqual({ ...saved, outputInvalidated: true })
      expect(bridge.confirm).not.toHaveBeenCalled()
      if (name === 'add source') expect(state.sources.some((source) => source.text === '新增事实' && !source.parsing)).toBe(true)
    })

  it.each([false, true])('recovers an old receipt by its original IDs before new model work (confirmed=%s)', async (confirmed) => {
    const bridge = installBillingBridge()
    seedPaidResult(confirmed)
    useStore.getState().setSourceProductName('product', '新产品')
    const newSession = useStore.getState().analysisSessionId
    const receiptIds: string[] = []
    bridge.api.confirmSavedModelResult = vi.fn((receipt) => {
      const persisted = bridge.persisted()!
      // Mirrors the unchanged main-process lookup: an original logical ID must
      // still resolve to its complete raw proof even in a new business session.
      const task = persisted.taskJournal?.[receipt.logicalTaskId] || Object.values(persisted.taskJournal || {})
        .find((entry) => entry.billingLogicalTaskId === receipt.logicalTaskId)
      expect(persisted.analysisSessionId).toBe(newSession)
      expect(task?.status).toBe('complete')
      expect(task?.billingAttemptId).toBe(receipt.requestId)
      if (receipt.logicalTaskId === taskId) {
        expect(task).toMatchObject({ output: productOutput, billingOutputSha256: productDigest, outputInvalidated: true })
        expect(useStore.getState().artifacts[1]).toBeUndefined()
      }
      receiptIds.push(receipt.logicalTaskId)
      return Promise.resolve({ state: 'charged', chargedUnits: 1_000_000 })
    })
    const newOutput = productOutput.replace(/已提供的产品事实/gu, '新输入对应的产品事实')
    bridge.api.sendChat = (_messages, context, handlers) => {
      bridge.modelCalls.push(context)
      expect(context.reportSessionId).toBe(newSession)
      expect(context.billingRequestId).not.toBe(taskId)
      expect(useStore.getState().taskJournal[taskId]?.billingConfirmed).toBe(true)
      queueMicrotask(() => context.taskType === 'module_product_info'
        ? handlers.onDone?.(newOutput, 'new-product', createHash('sha256').update(newOutput).digest('hex'))
        : handlers.onDone?.('暂无分析：没有额外证据。'))
      return { abort: () => undefined }
    }
    await useStore.getState()._runAnalysis()
    expect(receiptIds.filter((id) => id === taskId)).toHaveLength(confirmed ? 0 : 1)
    expect(useStore.getState().taskJournal[taskId]).toMatchObject({ billingConfirmed: true, outputInvalidated: true, output: productOutput })
    expect(useStore.getState().artifacts[1]).toBe(newOutput)
    await bridge.api.saveLastProject(buildProjectSnapshot(useStore.getState()))
    useStore.setState(useStore.getInitialState(), true)
    await useStore.getState().init()
    expect(useStore.getState().analysisSessionId).toBe(newSession)
    expect(useStore.getState().artifacts[1]).toBe(newOutput)
    expect(useStore.getState().moduleStates['product-info']?.status).toBe('done')
  })

  it('does not start new model work while a historical receipt is still ambiguous', async () => {
    const bridge = installBillingBridge()
    seedPaidResult(false)
    useStore.getState().setMaterialProductSelection(['新产品'])
    await useStore.getState()._runAnalysis()
    expect(bridge.confirm).toHaveBeenCalledTimes(1)
    expect(bridge.modelCalls).toHaveLength(0)
    expect(useStore.getState().taskJournal[taskId]).toMatchObject({ outputInvalidated: true, billingConfirmed: false })
    expect(useStore.getState().moduleStates['product-info']).toBeUndefined()
    expect(useStore.getState().phase).toBe('checkpoint1')
  })

  it('allows an existing local file read to finish when metadata changes before any new model task', async () => {
    const bridge = installBillingBridge()
    seedPaidResult(true)
    let releaseParse!: (value: { ok: boolean; text: string }) => void
    Object.assign(bridge.api, { parseFile: () => new Promise((resolve) => { releaseParse = resolve }) })
    const parsing = useStore.getState().addSources([{
      name: '新增资料.md', size: 4, arrayBuffer: () => Promise.resolve(new ArrayBuffer(4))
    } as File])
    await vi.waitFor(() => expect(releaseParse).toBeTypeOf('function'))
    const newSession = useStore.getState().analysisSessionId
    useStore.getState().setSourceNote('product', '新资料读取期间修改备注')
    releaseParse({ ok: true, text: '新资料解析完成' })
    await parsing
    expect(useStore.getState().analysisSessionId).toBe(newSession)
    expect(useStore.getState().sources.some((source) => source.text === '新资料解析完成' && !source.parsing)).toBe(true)
    expect(useStore.getState().taskJournal[taskId]?.outputInvalidated).toBe(true)
  })
})
