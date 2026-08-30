# 产品经营报告工具 — 重构开发仓库

本仓库从 `szhou4622/product-operation-report-app` 的正式发布基线 `v1.1.1` (`a7742aa45db1dee1098bc6524ffea38d12fb9311`) 迁入，后续架构收口与持续开发在这里进行。

## 当前开发阶段

当前处于 **Phase 0：Architecture Closure**。

Phase 0 只做：

- 当前 V2 生产路径收口
- ProductPolicy 单一真相
- Active / Legacy 分类
- Architecture Guard
- 日常 CI
- 请求、能力、非回归与迁移契约文档

Phase 0 不做 Task Engine、客户端 SQLite、Adaptive Planner、服务器 request status/cancel/reconcile 等后续重构。

## 当前架构文档

- [Active V2 Path](product-operation-report-app/docs/architecture/ACTIVE_PATH.md)
- [Product Policy](product-operation-report-app/docs/architecture/POLICY_SPEC.md)
- [Legacy Map](product-operation-report-app/docs/architecture/LEGACY_MAP.md)
- [Request Protocol](product-operation-report-app/docs/architecture/REQUEST_PROTOCOL.md)
- [Capability Contract](product-operation-report-app/docs/architecture/CAPABILITY_CONTRACT.md)
- [Non-regression Contract](product-operation-report-app/docs/architecture/NON_REGRESSION.md)
- [Migration Plan](product-operation-report-app/docs/architecture/MIGRATION_PLAN.md)

## 开发门禁

普通 PR / main push 会运行日常 CI：

```text
npm ci
npm run typecheck
npm run lint
npm run test:architecture
npm run test:unit
npm run test:regression
npm run build
```

正式 Tag 仍走独立桌面安装包构建与发版 Workflow。
