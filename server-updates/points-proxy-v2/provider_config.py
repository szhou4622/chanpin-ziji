"""Shared, non-secret Ark routing defaults for the proxy and key rotation tool."""

MANAGED_MODEL = "doubao-seed-2-1-pro-260915"
ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
ALLOWED_MODELS = (MANAGED_MODEL,)

# CNY per million tokens: standard online inference, not batch/low priority.
# https://docs.volcengine.com/docs/ark/model-pricing?lang=en&redirect=1
ARK_MODEL_PRICES_CNY = (6.0, 30.0, 1.2, 6.0)
