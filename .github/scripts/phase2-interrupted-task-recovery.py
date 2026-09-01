from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new)

# Canonical recovery: orphaned RUNNING is not a generic pause. It was interrupted
# because the process that owned the execution disappeared.
task_model_path = Path('product-operation-report-app/src/shared/taskModel.ts')
task_model = task_model_path.read_text(encoding='utf-8')
task_model = replace_once(
    task_model,
    '''    projected[taskId] = canonical.executionStatus === 'RUNNING'\n      ? {\n          ...canonical,\n          executionStatus: 'PAUSED',\n          resultStatus: undefined,\n          retryAt: undefined,\n          endedAt: undefined\n        }\n      : canonical\n''',
    '''    projected[taskId] = canonical.executionStatus === 'RUNNING'\n      ? {\n          ...canonical,\n          executionStatus: 'PAUSED',\n          resultStatus: undefined,\n          retryAt: undefined,\n          errorClass: 'PROCESS_INTERRUPTED',\n          endedAt: undefined\n        }\n      : canonical\n''',
    'mark orphaned running task interrupted',
)
task_model = replace_once(
    task_model,
    ''' * - A persisted RUNNING task is recovered as PAUSED because the process that owned\n *   the execution no longer exists after application restart.\n''',
    ''' * - A persisted RUNNING task is recovered as PAUSED with PROCESS_INTERRUPTED because\n *   the process that owned the execution no longer exists after application restart.\n''',
    'task recovery contract comment',
)
task_model_path.write_text(task_model, encoding='utf-8')

# Lock the recovery reason without changing successful/failed sibling tasks.
test_path = Path('product-operation-report-app/src/shared/taskModel.test.ts')
test = test_path.read_text(encoding='utf-8')
test = replace_once(
    test,
    '''    expect(reconciled[running.id]).toMatchObject({\n      executionStatus: 'PAUSED',\n      startedAt: running.startedAt,\n      migratedFromLegacy: false\n    })\n''',
    '''    expect(reconciled[running.id]).toMatchObject({\n      executionStatus: 'PAUSED',\n      errorClass: 'PROCESS_INTERRUPTED',\n      startedAt: running.startedAt,\n      migratedFromLegacy: false\n    })\n    expect(reconciled[failed.id]).toMatchObject({ executionStatus: 'FAILED', errorClass: 'NETWORK' })\n''',
    'task recovery test',
)
test_path.write_text(test, encoding='utf-8')

# Make the user-facing recovery instruction match actual execution semantics:
# completed modules are retained; continuing only runs incomplete work.
store_path = Path('product-operation-report-app/src/renderer/src/store.ts')
store = store_path.read_text(encoding='utf-8')
store = replace_once(
    store,
    "text: '上次任务在执行过程中退出了，已恢复保存好的资料和完整结果。请检查后重新开始。'",
    "text: '上次任务在执行过程中退出了，已恢复保存好的资料和完整结果。已完成模块不会重跑；请检查资料后点“确认，继续分析”，软件只会续跑未完成模块。'",
    'last project interruption message',
)
store = replace_once(
    store,
    "text: '上一份分析在执行过程中退出了，已恢复已保存的内容。请检查资料后重新开始。'",
    "text: '上一份分析在执行过程中退出了，已恢复已保存的内容。已完成模块不会重跑；请检查资料后继续分析，软件只会续跑未完成模块。'",
    'previous project interruption message',
)
store_path.write_text(store, encoding='utf-8')
