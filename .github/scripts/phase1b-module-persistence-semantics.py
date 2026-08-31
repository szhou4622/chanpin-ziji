from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new)

store = Path('product-operation-report-app/src/renderer/src/store.ts')
text = store.read_text(encoding='utf-8')

text = replace_once(
    text,
    "import { completeModuleAsInsufficient } from './store/moduleOutcome'\n",
    """import { completeModuleAsInsufficient } from './store/moduleOutcome'
import {
  completedModulePersistenceWarning,
  persistCompletedModuleSnapshot
} from './store/modulePersistence'
""",
    'module persistence import'
)

text = replace_once(
    text,
    """    const moduleByKey = new Map(REPORT_MODULES.map((module) => [module.key, module]))
    const activeModuleShadowTaskIds = new Map<ModuleKey, string>()
    const runModule = async (module: typeof REPORT_MODULES[number]): Promise<void> => {
""",
    """    const moduleByKey = new Map(REPORT_MODULES.map((module) => [module.key, module]))
    const activeModuleShadowTaskIds = new Map<ModuleKey, string>()
    const persistCompletedModuleState = async (module: typeof REPORT_MODULES[number]): Promise<void> => {
      const persisted = await persistCompletedModuleSnapshot(
        () => window.api.saveLastProject(buildProjectSnapshot(get()))
      )
      if (!persisted.ok && isCurrentSession()) {
        get()._post(
          'assistant',
          completedModulePersistenceWarning(
            `M${module.id} ${module.title}`,
            friendlyError(persisted.error)
          ),
          'error'
        )
      }
    }
    const runModule = async (module: typeof REPORT_MODULES[number]): Promise<void> => {
""",
    'module persistence boundary helper'
)

text = replace_once(
    text,
    """        })
        await window.api.saveLastProject(buildProjectSnapshot(get()))
        return output
      }
""",
    """        })
        await persistCompletedModuleState(module)
        return output
      }
""",
    'insufficient completion persistence'
)

text = replace_once(
    text,
    """      updateModuleState(module.key, { status: 'done', updatedAt: completedAt })
      await window.api.saveLastProject(buildProjectSnapshot(get()))
    }

    const executionBatches = buildModuleExecutionBatches(REPORT_MODULES)
""",
    """      updateModuleState(module.key, { status: 'done', updatedAt: completedAt })
      await persistCompletedModuleState(module)
    }

    const executionBatches = buildModuleExecutionBatches(REPORT_MODULES)
""",
    'valid completion persistence'
)

store.write_text(text, encoding='utf-8')
