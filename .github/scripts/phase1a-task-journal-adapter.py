from pathlib import Path

path = Path('product-operation-report-app/src/renderer/src/store.ts')
text = path.read_text(encoding='utf-8')

import_anchor = "import { isTemporaryReservationContention, planCleaningConcurrency } from './store/cleaning'\n"
import_line = "import { removeTaskJournalEntries, writeTaskJournalEntry } from './store/taskJournalAdapter'\n"
if import_line not in text:
    if text.count(import_anchor) != 1:
        raise SystemExit(f'import anchor count={text.count(import_anchor)}')
    text = text.replace(import_anchor, import_anchor + import_line)

replacements = [
(
"""                  taskJournal: {
                    ...state.taskJournal,
                    [batchTaskId]: {
                      kind: 'source_clean',
                      status: 'complete',
                      output: verifiedText,
                      updatedAt: new Date().toISOString()
                    }
                  },
""",
"""                  taskJournal: writeTaskJournalEntry(state.taskJournal, batchTaskId, {
                    kind: 'source_clean',
                    status: 'complete',
                    output: verifiedText
                  }),
"""
),
(
"""          taskJournal: {
            ...state.taskJournal,
            [savedTaskId]: { kind: 'module', status: 'failed', output: result.text, inputFingerprint, updatedAt: new Date().toISOString() }
          }
""",
"""          taskJournal: writeTaskJournalEntry(state.taskJournal, savedTaskId, {
            kind: 'module', status: 'failed', output: result.text, inputFingerprint
          })
"""
),
(
"""          taskJournal: {
            ...state.taskJournal,
            [savedTaskId]: { kind: 'module', status: 'failed', output: moduleOutput, inputFingerprint, updatedAt: new Date().toISOString() }
          }
""",
"""          taskJournal: writeTaskJournalEntry(state.taskJournal, savedTaskId, {
            kind: 'module', status: 'failed', output: moduleOutput, inputFingerprint
          })
"""
),
(
"""          taskJournal: {
            ...state.taskJournal,
            [savedTaskId]: { kind: 'module', status: 'complete', output, inputFingerprint, updatedAt: new Date().toISOString() }
          }
""",
"""          taskJournal: writeTaskJournalEntry(state.taskJournal, savedTaskId, {
            kind: 'module', status: 'complete', output, inputFingerprint
          })
"""
),
(
"""        taskJournal: {
          ...state.taskJournal,
          [savedTaskId]: { kind: 'module', status: 'complete', output: moduleOutput, inputFingerprint, updatedAt: new Date().toISOString() }
        }
""",
"""        taskJournal: writeTaskJournalEntry(state.taskJournal, savedTaskId, {
          kind: 'module', status: 'complete', output: moduleOutput, inputFingerprint
        })
"""
),
(
"""          taskJournal: {
            ...state.taskJournal,
            [taskId]: { kind: 'module', status: 'failed', updatedAt: new Date().toISOString() }
          }
""",
"""          taskJournal: writeTaskJournalEntry(state.taskJournal, taskId, {
            kind: 'module', status: 'failed'
          })
"""
),
(
"""      taskJournal: Object.fromEntries(Object.entries(state.taskJournal).filter(([taskId]) =>
        ![...affected].some((moduleKey) => taskId.includes(`:module:v2:${moduleKey}`))
      )),
""",
"""      taskJournal: removeTaskJournalEntries(
        state.taskJournal,
        (taskId) => [...affected].some((moduleKey) => taskId.includes(`:module:v2:${moduleKey}`))
      ),
"""
)
]

for old, new in replacements:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'expected one replacement, found {count}: {old[:120]!r}')
    text = text.replace(old, new)

path.write_text(text, encoding='utf-8')
