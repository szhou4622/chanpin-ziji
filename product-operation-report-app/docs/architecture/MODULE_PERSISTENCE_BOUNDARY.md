# Module Persistence Boundary

## 目标

模块业务执行结果与本地项目快照保存结果必须是两个不同维度。

一个模块已经得到合法模型输出并完成 validator 后：

- 模块执行状态已经成功；
- canonical shadow Task 已经进入 `SUCCEEDED`；
- legacy module state 已经进入 `done` / `skipped`；
- 随后的 `saveLastProject()` 失败不得把模块反向改成 `FAILED`。

## 当前边界

v2 模块完成后走：

```text
Model / local outcome completed
        ↓
commit module result in renderer memory
        ↓
Task = SUCCEEDED + VALID / INSUFFICIENT
        ↓
try save full project snapshot
        ├─ success → no extra action
        └─ failure → persistence warning only
```

持久化失败时：

1. 不删除当前模块结果；
2. 不修改 `moduleStates` 为 failed；
3. 不把 shadow Task 从 SUCCEEDED 改为 FAILED；
4. 不让错误继续抛到模块 `Promise.allSettled()`；
5. UI 明确提示本地自动保存失败，并提醒暂时不要关闭软件；
6. 后续模块完成、最终报告完成等保存点仍会再次写入整份项目快照。

## 当前覆盖范围

本阶段只修改两类“模块已完成之后”的强制保存：

- `SUCCEEDED + VALID`
- `SUCCEEDED + INSUFFICIENT`

模型请求失败、validator 失败等真正执行失败仍按原路径进入 FAILED。

最终报告保存、项目新建/归档、设置保存等其它持久化路径不在本次修改范围内。

## 为什么不能简单吞掉所有保存错误

持久化失败是真实故障，只是它不是“模块分析失败”。因此当前策略是：

- 执行状态保持真实；
- 保存错误明确展示；
- 利用后续整项目快照保存自然重试；
- 后续 Recovery/Persistence 层再引入更完整的 dirty-state、retry queue 或 durable checkpoint。

## 后续目标

当 Task Engine / Recovery Manager 接管后，应进一步把状态拆成类似：

```text
ExecutionStatus: SUCCEEDED
ResultStatus: VALID
PersistenceStatus: DIRTY | SAVED | SAVE_FAILED
```

本阶段不新增第三套持久化状态机，只先阻止错误的状态反向污染。
