from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new)

path = Path('product-operation-report-app/src/main/sourceCleanCache.ts')
text = path.read_text(encoding='utf-8')
text = replace_once(
    text,
    "import { SOURCE_CLEAN_PROMPT_VERSION, TABLE_DIGEST_VERSION } from '../shared/reportVersions'\n",
    "import { SOURCE_CLEAN_PROMPT_VERSION, TABLE_DIGEST_VERSION } from '../shared/reportVersions'\nimport { EVIDENCE_ID_VERSION } from '../shared/evidenceIdentity'\n",
    'evidence identity cache version import',
)
text = replace_once(
    text,
    "  for (const value of [\n    SOURCE_CLEAN_PROMPT_VERSION, TABLE_DIGEST_VERSION, safeString(model, 200).trim().toLowerCase(),\n",
    "  for (const value of [\n    EVIDENCE_ID_VERSION, SOURCE_CLEAN_PROMPT_VERSION, TABLE_DIGEST_VERSION, safeString(model, 200).trim().toLowerCase(),\n",
    'evidence identity cache version',
)
path.write_text(text, encoding='utf-8')
