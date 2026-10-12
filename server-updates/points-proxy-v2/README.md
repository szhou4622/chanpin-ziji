# 正式 V2 代理的豆包迁移

本目录保留 2026-10-12 正式服务器已有的 V2 精确积分实现，在该实现上接入
`doubao-seed-2-1-pro-260915`。不要用 legacy 的 `points-proxy-v1` 覆盖正式服务。

原正式代理 SHA256：`460ce2d6c5c3984a0e339a2451fc0536bc2b0289b53e9683e4d8a2d4aa5039c4`。
`por_billing_v2.py` 和 `provider_keyring.py` 保留服务器原实现。

- 所有新模型任务实际调用方舟豆包 2.1 Pro。已有安装包发送的五个旧模型名称仅作为兼容别名，服务器在验证时转为豆包，不再请求旧供应商。
- 普通任务使用 Chat API。清洗、摘要关闭思考；分析任务开启思考。输出及思维链共同受 `max_completion_tokens` 限制。
- M4 使用 Responses API，开启思考和基础联网搜索。搜索来源继续通过代理可信事件返回。
- 支持结果确认的客户端仍在结果完整且本地保存确认之后扣费；失败或不完整输出不生成成功证明。旧客户端继续使用既有 legacy 结算模式。
- 使用带 SHA256 校验的 `ark-standard-20261012.json`，以人民币按实际 Token 计费：非缓存输入 6 元、输出 30 元、缓存命中 1.2 元/百万 Token。继续使用服务器原积分倍率、四舍五入、中央账本和幂等行为。
- 旧模型价格只用于历史待结算记录，按原固定 7.2 汇率转换后保留；不会重新收费或追收历史任务。V2 仍按原合同仅向用户收取模型 Token 费用，搜索资源费由平台承担。
- Key 仅保存在服务器 `/etc/product-operation-report/provider-keys.json`。不要写入仓库、客户端或安装包。

部署前运行 `python -B -m unittest -v test_ark_v2.py`，验证真实回环 HTTP、全部任务、旧模型别名、结果确认、重复确认和中断零扣费。
部署必须备份正式代码、Key 配置和计费环境；升级代码与价目表后重启正式服务，验证公网健康、真实模型调用和精确积分确认。

接口及计价来源：[官方模型价格](https://docs.volcengine.com/docs/ark/model-pricing?lang=en&redirect=1)、[深度思考](https://docs.volcengine.com/docs/ark/deep-thinking?lang=en)、[联网搜索](https://docs.volcengine.com/docs/ark/web-search?lang=en)。
