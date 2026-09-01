import { describe, expect, it } from 'vitest'
import { buildCleaningPlan } from './cleaningPlan'
import { buildSourceCleanBatchPlan } from './sourceCleanBatches'

describe('cleaning planner', () => {
  it('keeps a large ragged profile table local and free of model jobs', () => {
    const text = [
      '标签类型,标签,占比',
      ...Array.from({ length: 3_049 }, (_, index) => index === 677
        ? `电商品类成交偏好,标签${index + 1},0%,14.53%`
        : `电商品类成交偏好,标签${index + 1},${index % 100}%`)
    ].join('\n')
    const plan = buildCleaningPlan([{ id: 'profile', name: '画像.csv', kind: 'table', text }])
    expect(plan.localFileCount).toBe(1)
    expect(plan.expectedModelJobs).toBe(0)
    expect(plan.entries[0].method).toBe('local_exact')
  })

  it('sends every semantic row exactly once without planning per-row outputs', () => {
    const text = [
      '评价内容,评分',
      ...Array.from({ length: 3_000 }, (_, index) => `第${index + 1}条评价-${'具体使用感受'.repeat(12)},${index % 5 + 1}`)
    ].join('\n')
    const plan = buildCleaningPlan([{ id: 'reviews', name: '评价.csv', kind: 'table', text }])
    expect(plan.entries[0].method).toBe('model_semantic')
    expect(plan.expectedModelJobs).toBeGreaterThan(1)
    const batches = buildSourceCleanBatchPlan({ name: '评价.csv', kind: 'table', text }, { semanticSummary: true }).batches
    const ids = batches.flatMap((batch) => batch.context.evidenceIds)
    expect(ids).toHaveLength(3_000)
    expect(new Set(ids).size).toBe(3_000)
    expect(batches.every((batch) => batch.context.mode === 'semantic_rows')).toBe(true)
    expect(batches.every((batch) => Boolean(batch.context.coverageReceipt))).toBe(true)
  })

  it('routes a workbook to semantic cleaning when a later worksheet contains raw reviews', () => {
    const text = [
      '### 工作表：经营汇总',
      '商品名称,成交金额,成交订单数,评价好评率',
      '产品A,1000,20,98%',
      '',
      '### 工作表：用户评价',
      '评价内容,评分',
      '很好用，老人也能看懂,5',
      '包装有点难拆,3'
    ].join('\n')
    const plan = buildCleaningPlan([{ id: 'mixed-workbook', name: '经营与评价.xlsx', kind: 'table', text }])
    expect(plan.entries[0].method).toBe('model_semantic')
    expect(plan.expectedModelJobs).toBeGreaterThan(0)
  })

  it('keeps a multi-sheet workbook local when every worksheet is aggregate metrics only', () => {
    const text = [
      '### 工作表：商品经营',
      '商品名称,成交金额,成交订单数',
      '产品A,1000,20',
      '',
      '### 工作表：人群汇总',
      '年龄段,人数,占比',
      '31-40,100,40%'
    ].join('\n')
    const plan = buildCleaningPlan([{ id: 'metrics-workbook', name: '经营汇总.xlsx', kind: 'table', text }])
    expect(plan.entries[0].method).toBe('local_exact')
    expect(plan.expectedModelJobs).toBe(0)
  })

  it('plans fifty standard business tables with zero model cleaning', () => {
    const text = '商品名称,成交金额,成交订单数\n产品A,100,2\n产品B,200,3'
    const sources = Array.from({ length: 50 }, (_, index) => ({
      id: `table-${index + 1}`,
      name: `商品-${index + 1}.csv`,
      kind: 'table' as const,
      text
    }))
    const plan = buildCleaningPlan(sources)
    expect(plan.localFileCount).toBe(50)
    expect(plan.modelFileCount).toBe(0)
    expect(plan.expectedModelJobs).toBe(0)
  })

  it('does not mistake numeric evaluation metrics for raw review text', () => {
    const text = [
      '商品名称,成交金额,成交订单数,评价好评率,评价差评率,商品差评订单数,投诉工单量',
      '产品A,1000,20,98%,2%,1,0',
      '产品B,800,15,97%,3%,1,0'
    ].join('\n')
    const plan = buildCleaningPlan([{ id: 'products', name: '经营版_商品列表.xlsx', kind: 'table', text }])
    expect(plan.entries[0].method).toBe('local_exact')
    expect(plan.expectedModelJobs).toBe(0)
  })
})
