from pathlib import Path

path = Path('product-operation-report-app/scripts/regression-main.ts')
text = path.read_text(encoding='utf-8')
anchor = """  assert.equal(restoredTaskBridge?.taskRecords?.['module:voc:legacy']?.resultStatus, 'VALID', 'legacy complete task projects to VALID')
  assert.equal(restoredTaskBridge?.taskRecords?.['module:voc:legacy']?.inputFingerprint, 'voc-input-v1', 'task input identity survives project persistence')
"""
insert = anchor + """
  const canonicalTaskId = 'module:voc:canonical'
  const canonicalTaskUpdatedAt = '2026-08-20T03:10:00.000Z'
  const canonicalTaskSnapshot: SavedProject = {
    ...snapshot(7, ''),
    taskJournal: {
      [canonicalTaskId]: {
        kind: 'module',
        status: 'complete',
        output: '暂无分析：当前VOC证据不足',
        inputFingerprint: 'voc-input-v2',
        updatedAt: canonicalTaskUpdatedAt
      }
    },
    taskRecords: {
      [canonicalTaskId]: {
        schemaVersion: 1,
        id: canonicalTaskId,
        kind: 'MODULE_ANALYSIS',
        executionStatus: 'SUCCEEDED',
        resultStatus: 'INSUFFICIENT',
        dependencies: [],
        inputFingerprint: 'voc-input-v2',
        moduleKey: 'voc',
        attemptCount: 0,
        createdAt: '2026-08-20T03:09:00.000Z',
        updatedAt: canonicalTaskUpdatedAt,
        endedAt: canonicalTaskUpdatedAt,
        migratedFromLegacy: false
      }
    }
  }
  await saveLastProject(canonicalTaskSnapshot)
  const restoredCanonicalTask = await loadLastProject()
  assert.equal(restoredCanonicalTask?.taskRecords?.[canonicalTaskId]?.resultStatus, 'INSUFFICIENT', 'canonical insufficient result survives project persistence')
  assert.equal(restoredCanonicalTask?.taskRecords?.[canonicalTaskId]?.migratedFromLegacy, false, 'validated canonical runtime metadata is preserved')

  await saveLastProject({
    ...canonicalTaskSnapshot,
    taskRecords: {
      [canonicalTaskId]: {
        ...canonicalTaskSnapshot.taskRecords![canonicalTaskId],
        id: 'tampered-task-id'
      }
    }
  })
  const restoredTamperedTask = await loadLastProject()
  assert.equal(restoredTamperedTask?.taskRecords?.[canonicalTaskId]?.resultStatus, 'VALID', 'malformed canonical metadata falls back to journal projection')
  assert.equal(restoredTamperedTask?.taskRecords?.[canonicalTaskId]?.migratedFromLegacy, true, 'fallback projection is explicitly marked legacy-derived')
"""
if text.count(anchor) != 1:
    raise SystemExit(f'expected one task bridge regression anchor, found {text.count(anchor)}')
path.write_text(text.replace(anchor, insert), encoding='utf-8')
