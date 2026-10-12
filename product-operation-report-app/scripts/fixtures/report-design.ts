import type { MaterialSellingPointInsight } from '../../src/shared/types'

/** Synthetic, labelled data for visual regression. Never used for merchant analysis. */
export function merchantDesignFixture(product: string, brand: string): string {
  return `# 版式演示（合成测试数据）

## M1 产品信息
1. 产品基础
信息：${product}；品牌${brand}。
来源：合成测试手卡
2. SKU规格
信息：标准装与便携装两种规格。
来源：合成测试手卡
3. 价格
信息：测试价99元。
来源：合成测试价格表
4. 原料/成分/材质
信息：详细信息以产品手卡为准。
来源：合成测试手卡

## M2 成交人群分析
${['视频号', '抖店罗盘', '巨量云图'].map((platform, index) => `
### 平台：${platform}
### 1. 性别
信息：女性${68 + index * 3}%，男性${32 - index * 3}%
来源：${platform}合成画像
### 2. 年龄
信息：31-40岁42%，41-50岁28%，其他30%
来源：${platform}合成画像
### 3. 地域
信息：江苏18%，浙江15%，广东12%
来源：${platform}合成画像
### 4. 人群属性
信息：精致妈妈36%，资深中产24%
来源：${platform}合成画像`).join('\n')}
### 多平台核心人群TOP5
| 优先级 | 人群标签 | 占比/特征 | 决策动机 | 内容语言 |
|---|---|---|---|---|
| 第一主力 | 31-40岁女性｜家庭决策者 | 三个平台均有来源 | 日常选择更看重省心、稳定和使用体验 | 日常场景＋使用便利 |
| 第二主力 | 36-50岁品质用户 | 测试样本人群 | 关注品质依据，也关注实际使用感受 | 品质细节＋使用证明 |
| 第三人群 | 成熟生活用户 | 测试样本人群 | 偏好熟悉且容易理解的产品表达 | 熟悉场景＋简单表达 |

## M3 内容素材判断
### 自有素材TOP1｜使用展示型
框架类型：日常场景｜问题引入｜使用展示｜结果呈现
数据依据：8条｜占自有素材40%
可复用方向：展示真实使用步骤，把核心体验讲清楚。
### 自有素材TOP2｜细节说明型
框架类型：细节切入｜产品说明｜体验展示
数据依据：6条｜占自有素材30%
可复用方向：围绕一处可核对的细节展开说明。
### 竞品素材TOP1｜场景对比型
框架类型：场景问题｜使用前后｜体验说明
数据依据：5条｜占竞品素材25%
可复用方向：借鉴讲述结构，不移用竞品的产品宣称。
### 补充机会TOP1｜问答解释型
机会框架：顾虑提问｜事实说明｜使用建议
竞品依据：3条
可补充方向：选择常见疑问，提供可核对的回答。

## M4 卖点提炼与排序
### 一、四大需求卖点买点摘要
### 1. 品质需求
TOP1
卖点：产品细节清晰
买点：能够判断是否适合日常使用
来源：合成测试资料
### 2. 价格需求
TOP1
卖点：提供多种规格
买点：按实际使用场景选择
来源：合成测试资料
### 3. 健康需求
无
### 4. 情感需求
TOP1
卖点：融入日常生活
买点：减少选择和使用的负担
来源：合成测试资料
### 二、用户视角卖点排序TOP10
TOP1
用户视角卖点：使用更方便
对应产品事实：步骤简单
打动的人群/场景：日常使用
作用：帮助理解
来源：合成测试资料

## M5 用户真实需求VOC
### 一、正面反馈TOP10
TOP1
用户原话：用起来很方便。
出现次数：6
需求解读：希望减少准备步骤
来源：合成测试评论
### 二、痛点TOP10
TOP1
用户原话：第一次使用希望有清楚的说明。
出现次数：4
需求解读：需要更明确的使用指引
来源：合成测试评论
### 三、顾虑TOP10
TOP1
用户原话：希望能看清楚具体规格。
出现次数：3
需求解读：希望比较不同规格
来源：合成测试评论
### 四、期待TOP10
TOP1
用户原话：想看更多日常用法。
出现次数：3
需求解读：需要场景示范
来源：合成测试评论

## M6 人群×卖点×场景匹配
TOP1
核心人群：家庭决策者
核心卖点：使用更方便
真实场景：家庭日常使用
场景状态：测试样例
人群来源：合成画像
卖点来源：合成产品手卡
场景依据：合成测试评论

> 本报告内容由 AI 生成，请谨慎参考。
`
}

export function cloudDesignFixture(): MaterialSellingPointInsight {
  const words = ['快手做菜', '脆爽口感', '配料简单', '开袋即用', '家庭分享', '独立小包装', '方便储存', '家常风味', '多种做法', '价格实惠', '规格清晰', '拌饭搭配', '节省准备时间', '质地清爽', '日常补货', '食材搭配', '做法丰富', '便于携带', '包装整洁', '味道熟悉']
  return { version: 1, sourceScope: 'own', fingerprint: 'design-fixture', scopeLabel: '合成测试素材',
    totalMaterials: 20, effectiveMaterials: 20, normalizedCount: words.length, mappings: [],
    items: words.map((keyword, index) => ({ keyword, materialCount: Math.max(1, 12 - index),
      coverageRate: Math.max(1, 12 - index) / 20, top1Count: Math.max(1, 12 - index),
      top2Count: 0, top3Count: 0, unrankedCount: 0, rankScore: Math.max(1, 12 - index) * 3,
      evidence: [{ sourceId: 'sample-own', sourceName: '合成测试素材.csv', sheetName: '测试',
        rowEvidenceId: `POR-R-DEMO0000-${String(index + 1).padStart(6, '0')}`, materialKey: `sample-${index}`,
        rawDescription: `测试原话：${keyword}，适合日常使用。`, evidenceSnippet: keyword,
        candidate: keyword, keyword, topRank: 1 }] })) }
}
