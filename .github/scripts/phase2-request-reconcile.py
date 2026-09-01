from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new)

# 1) Make logical-task admission atomic inside ProxyRequestTracker.
lifecycle_path = Path('product-operation-report-app/src/main/proxyRequestLifecycle.ts')
lifecycle = lifecycle_path.read_text(encoding='utf-8')
lifecycle = replace_once(
    lifecycle,
    '''  claim(rootRequestId: string, ownerId: number, taskKey: string): void {\n    const root = assertSafeProxyRequestId(rootRequestId)\n    const safeTaskKey = assertSafeProxyTaskKey(taskKey)\n    if (this.entries.has(root)) throw new Error('检测到重复的代理请求跟踪记录。')\n    this.entries.set(root, { rootRequestId: root, ownerId, taskKey: safeTaskKey })\n  }\n\n  setCurrent(rootRequestId: string, ownerId: number, requestId: string): boolean {\n''',
    '''  claim(rootRequestId: string, ownerId: number, taskKey: string): void {\n    const root = assertSafeProxyRequestId(rootRequestId)\n    const safeTaskKey = assertSafeProxyTaskKey(taskKey)\n    if (this.entries.has(root)) throw new Error('检测到重复的代理请求跟踪记录。')\n    if (this.findByTaskKey(safeTaskKey)) throw new Error('同一模型任务正在处理中，请稍后重试。')\n    this.entries.set(root, { rootRequestId: root, ownerId, taskKey: safeTaskKey })\n  }\n\n  findByTaskKey(taskKey: string, excludeRootRequestId?: string): TrackedProxyRequest | undefined {\n    const safeTaskKey = assertSafeProxyTaskKey(taskKey)\n    let exclude = ''\n    if (excludeRootRequestId) {\n      try {\n        exclude = assertSafeProxyRequestId(excludeRootRequestId)\n      } catch {\n        exclude = ''\n      }\n    }\n    for (const [root, entry] of this.entries) {\n      if (root === exclude || entry.taskKey !== safeTaskKey) continue\n      return { ...entry }\n    }\n    return undefined\n  }\n\n  setCurrent(rootRequestId: string, ownerId: number, requestId: string): boolean {\n''',
    'ProxyRequestTracker logical task admission',
)
lifecycle_path.write_text(lifecycle, encoding='utf-8')

# 2) Add the control-plane reconcile facade to aiProxy.ts.
ai_path = Path('product-operation-report-app/src/main/aiProxy.ts')
ai = ai_path.read_text(encoding='utf-8')
ai = replace_once(
    ai,
    '''} from './proxyRequestLifecycle'\n\ninterface ProxySession {\n''',
    '''} from './proxyRequestLifecycle'\nimport { reconcileDetachedProxyTask } from './proxyRequestReconcile'\n\ninterface ProxySession {\n''',
    'aiProxy reconcile import',
)
ai = replace_once(
    ai,
    '''export async function cancelProxyTask(taskKey: string, preferredRequestId?: string): Promise<ProxyRequestState[]> {\n  const safeTaskKey = assertSafeProxyTaskKey(taskKey)\n  if (preferredRequestId) {\n    try {\n      const preferred = await cancelProxyRequest(preferredRequestId)\n      if (preferred.status === 'running') return [preferred]\n    } catch (error) {\n      if (!(error instanceof ProxyHttpError) || error.status !== 404) throw error\n    }\n  }\n  const active = await fetchActiveProxyRequests(safeTaskKey)\n  if (!active.length) return []\n  return Promise.all(active.map((request) => cancelProxyRequest(request.requestId)))\n}\n\nexport function clearAiProxySession(): void {\n''',
    '''export async function cancelProxyTask(taskKey: string, preferredRequestId?: string): Promise<ProxyRequestState[]> {\n  const safeTaskKey = assertSafeProxyTaskKey(taskKey)\n  if (preferredRequestId) {\n    try {\n      const preferred = await cancelProxyRequest(preferredRequestId)\n      if (preferred.status === 'running') return [preferred]\n    } catch (error) {\n      if (!(error instanceof ProxyHttpError) || error.status !== 404) throw error\n    }\n  }\n  const active = await fetchActiveProxyRequests(safeTaskKey)\n  if (!active.length) return []\n  return Promise.all(active.map((request) => cancelProxyRequest(request.requestId)))\n}\n\nexport async function reconcileProxyTaskBeforeSubmission(taskKey: string, signal: AbortSignal): Promise<void> {\n  const safeTaskKey = assertSafeProxyTaskKey(taskKey)\n  const outcome = await reconcileDetachedProxyTask(safeTaskKey, signal, {\n    listActive: fetchActiveProxyRequests,\n    cancel: cancelProxyRequest\n  })\n  if (outcome.status === 'ready') return\n  if (outcome.status === 'stopped') throw new Error('已停止')\n  if (outcome.status === 'pending') {\n    throw new Error('上一条模型任务仍在服务器结束中，为避免重复扣费，本次没有提交新请求。请稍后重试。')\n  }\n  throw new Error('无法确认上一条模型任务是否已结束，为避免重复扣费，本次没有提交新请求。请检查网络后重试。')\n}\n\nexport function clearAiProxySession(): void {\n''',
    'aiProxy reconcile facade',
)
ai_path.write_text(ai, encoding='utf-8')

# 3) Run reconcile before any managed-proxy upstream submission.
index_path = Path('product-operation-report-app/src/main/index.ts')
index = index_path.read_text(encoding='utf-8')
index = replace_once(
    index,
    '''  fetchProxyWallet,\n  testProxyHealth\n} from './aiProxy'\n''',
    '''  fetchProxyWallet,\n  reconcileProxyTaskBeforeSubmission,\n  testProxyHealth\n} from './aiProxy'\n''',
    'index reconcile import',
)
index = replace_once(
    index,
    '''          profiles = await authorizeProxyProfiles(profiles)\n        } catch (error) {\n''',
    '''          profiles = await authorizeProxyProfiles(profiles)\n          await reconcileProxyTaskBeforeSubmission(context.taskKey, controller.signal)\n        } catch (error) {\n''',
    'managed proxy pre-submission reconcile',
)
index_path.write_text(index, encoding='utf-8')

# 4) Preserve lifecycle-conflict meaning through renderer friendly errors.
errors_path = Path('product-operation-report-app/src/renderer/src/store/errors.ts')
errors = errors_path.read_text(encoding='utf-8')
errors = replace_once(
    errors,
    '''  if (/已停止|aborted|aborterror/i.test(raw)) return '已停止。'\n  if (/enospc|no space left|磁盘空间不足|磁盘已满/i.test(raw)) {\n''',
    '''  if (/已停止|aborted|aborterror/i.test(raw)) return '已停止。'\n  if (/HTTP\\s*409|same batch still processing|同一模型任务正在处理中|上一条模型任务.*(?:处理中|结束中)/iu.test(raw)) {\n    return '上一条模型任务仍在服务器处理中，请稍后重试。'\n  }\n  if (/无法确认上一条模型任务是否已结束|避免重复扣费.*检查网络/iu.test(raw)) {\n    return '网络连接失败，暂时无法确认上一条模型任务是否已结束；为避免重复扣费，本次没有提交新请求。'\n  }\n  if (/HTTP\\s*5\\d\\d|服务请求失败.*5\\d\\d/iu.test(raw)) {\n    const status = raw.match(/HTTP\\s*(5\\d\\d)/i)?.[1]\n    return status ? `模型服务暂时不可用（HTTP ${status}），请稍后重试。` : '模型服务暂时不可用，请稍后重试。'\n  }\n  if (/enospc|no space left|磁盘空间不足|磁盘已满/i.test(raw)) {\n''',
    'friendly reconcile errors',
)
errors_path.write_text(errors, encoding='utf-8')

# 5) Make retry classification explicit and allow a 409 only after it becomes a safe new admission cycle.
analysis_path = Path('product-operation-report-app/src/renderer/src/store/analysis.ts')
analysis = analysis_path.read_text(encoding='utf-8')
analysis = replace_once(
    analysis,
    '''export async function runModelRetry(\n''',
    '''export function shouldRetryModelRun(error = ''): boolean {\n  if (!error || /已停止|安全|内容过滤|积分不足|授权|403|401/i.test(error)) return false\n  return /fetch failed|ECONNRESET|ETIMEDOUT|socket hang up|terminated|network|网络连接失败|连接提前结束|服务繁忙|额度受限|429|HTTP\\s*5\\d\\d|超时|没有返回内容|未生成内容|空响应|empty[_ -]?output|response stream was interrupted|上一条模型任务仍在服务器处理中/i.test(error)\n}\n\nexport async function runModelRetry(\n''',
    'explicit retry classifier',
)
analysis = replace_once(
    analysis,
    '''  while (\n    !result.ok && retry < retries &&\n    !/已停止|安全|内容过滤|积分不足|授权|403|401/i.test(result.error || '') &&\n    /fetch failed|ECONNRESET|ETIMEDOUT|socket hang up|terminated|network|网络连接失败|连接提前结束|服务繁忙|额度受限|429|HTTP\\s*5\\d\\d|超时|没有返回内容|未生成内容|空响应|empty[_ -]?output|response stream was interrupted/i.test(result.error || '')\n  ) {\n''',
    '''  while (!result.ok && retry < retries && shouldRetryModelRun(result.error)) {\n''',
    'runModelRetry classifier usage',
)
analysis_path.write_text(analysis, encoding='utf-8')

# 6) Strengthen the local admission test now that claim is atomic by task key.
admission_test_path = Path('product-operation-report-app/src/main/proxyRequestAdmission.test.ts')
admission_test = admission_test_path.read_text(encoding='utf-8')
admission_test = replace_once(
    admission_test,
    '''    expect(tracker.findByTaskKey(taskKey)?.rootRequestId).toBe(first)\n    expect(tracker.findByTaskKey(taskKey, first)).toBeUndefined()\n\n    tracker.claim(second, 20, 'report-a:module:v2:voc')\n''',
    '''    expect(tracker.findByTaskKey(taskKey)?.rootRequestId).toBe(first)\n    expect(tracker.findByTaskKey(taskKey, first)).toBeUndefined()\n    expect(() => tracker.claim(second, 20, taskKey)).toThrow(/同一模型任务正在处理中/u)\n\n    tracker.claim(second, 20, 'report-a:module:v2:voc')\n''',
    'atomic local task admission test',
)
admission_test_path.write_text(admission_test, encoding='utf-8')
