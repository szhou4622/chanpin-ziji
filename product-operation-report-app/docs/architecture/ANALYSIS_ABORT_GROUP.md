# Analysis Abort Group

## 问题

v2 六模块第一波会并发执行多个模型请求，但 renderer 过去只有一个 `abortFn`。

每个 `runModelRetry()` 都会反复执行：

```text
setAbort(request abort)
→ request finished
→ setAbort(null)
→ retry delay 时 setAbort(timer abort)
→ setAbort(null)
→ 下一次 request abort
```

如果并发模块直接把这些句柄写进同一个 `StoreState.abortFn`，后注册的模块会覆盖前面的模块。用户点击“停止”时只能可靠取消最后一个句柄。

另外，旧执行循环没有整次分析的 cancelled 标记，即使当前请求被停止，也可能继续进入后续 M4 / M6 波次。

## 当前修复

每次 `_runAnalysis()` 创建一个独立 `AbortGroup`：

```text
Analysis parent abort
        ↓
AbortGroup
  ├─ M1 current abort handle
  ├─ M2 current abort handle
  ├─ M3 current abort handle
  └─ M5 current abort handle
```

每个模块拥有独立 registrar。

一个模块调用 `setAbort(null)` 时，只移除自己的当前句柄，不会清除其它模块。

用户点击停止：

1. parent group 标记 aborted；
2. 广播调用当前所有 child abort；
3. 之后新注册的 child abort 会立即执行，避免取消后又启动 retry/request；
4. 当前 wave `Promise.allSettled()` 收口后检查 parent aborted；
5. 分析回到 `checkpoint1`；
6. 不再启动后续 wave；
7. 已完成模块结果继续保留；
8. 未完成或已取消模块下次继续时重新执行。

## Validator retry

validator 自动补全本身也会调用 `runModelRetry()`。

用户在这个阶段停止时，结果必须保持取消语义：

```text
ExecutionStatus = CANCELLED
errorClass = USER_STOP
```

不能因为原始输出仍有 validation errors 而改写为 `FAILED / VALIDATION_FAILED`。

## 取消后的持久化

分析停止后会尝试保存当前完整项目快照。

如果这次保存失败：

- 停止状态仍然生效；
- 当前窗口结果仍保留；
- UI 明确提示本地快照保存失败；
- 不把保存错误改写成模型执行错误。

## 当前边界

本阶段只修 renderer 内部的并发取消语义。

没有修改：

- server request status / cancel API；
- provider 侧真实 cancellation；
- 断线 reconcile；
- 409 request lifecycle；
- billing identity / settlement；
- Scheduler ownership。

因此这一层解决的是：**本地一次分析里的所有并发请求都收到停止信号，并且停止后不再启动新模块。**

真正跨进程、跨 server/provider 的可靠取消仍属于后续 Request Lifecycle / Recovery 阶段。
