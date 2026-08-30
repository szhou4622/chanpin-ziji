from pathlib import Path

path = Path('product-operation-report-app/scripts/regression-main.ts')
text = path.read_text(encoding='utf-8')
anchor = "  assert.equal((await loadLastProject())?.analysisSessionId, 'stable-billing-session', 'crash recovery preserves stable billing ids')\n"
insert = """  const taskBridgeSnapshot: SavedProject = {\n    ...snapshot(7, ''),\n    taskJournal: {\n      'module:voc:legacy': {\n        kind: 'module',\n        status: 'complete',\n        output: '旧VOC结果',\n        inputFingerprint: 'voc-input-v1',\n        updatedAt: '2026-08-20T03:00:00.000Z'\n      }\n    }\n  }\n  await saveLastProject(taskBridgeSnapshot)\n  const restoredTaskBridge = await loadLastProject()\n  assert.equal(restoredTaskBridge?.taskJournal?.['module:voc:legacy']?.output, '旧VOC结果', 'legacy task journal output remains recoverable')\n  assert.equal(restoredTaskBridge?.taskRecords?.['module:voc:legacy']?.kind, 'MODULE_ANALYSIS', 'legacy journal projects into canonical task kind')\n  assert.equal(restoredTaskBridge?.taskRecords?.['module:voc:legacy']?.executionStatus, 'SUCCEEDED', 'legacy complete task projects to SUCCEEDED')\n  assert.equal(restoredTaskBridge?.taskRecords?.['module:voc:legacy']?.resultStatus, 'VALID', 'legacy complete task projects to VALID')\n  assert.equal(restoredTaskBridge?.taskRecords?.['module:voc:legacy']?.inputFingerprint, 'voc-input-v1', 'task input identity survives project persistence')\n"""
if text.count(anchor) != 1:
    raise SystemExit(f'expected one insertion anchor, found {text.count(anchor)}')
if insert.strip() not in text:
    text = text.replace(anchor, anchor + insert)
path.write_text(text, encoding='utf-8')
