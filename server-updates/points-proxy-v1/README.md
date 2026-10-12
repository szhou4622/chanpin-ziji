# ProductOperationReport 业务代理（待部署包）

本目录是业务代理部署源码；修改仓库不会自动部署服务器。它把供应商 API Key、请求预留、真实 Token 计价和每日费用上限放在 `127.0.0.1:8794`；授权服务器仍是余额、充值和最终扣费的唯一权威。公网只暴露：

- `POST /api/product-operation-report/v1/session`
- `GET /api/product-operation-report/v1/wallet`
- `POST /api/product-operation-report/v1/wallet/redeem`
- `POST /api/product-operation-report/v1/chat/completions`
- `GET /api/product-operation-report/v1/health`

部署前必须先让授权服务满足 [AUTHORIZATION_CONTRACT.md](AUTHORIZATION_CONTRACT.md)：返回严格布尔成功值、稳定 `code_id`、真实机器码、绑定状态、当前剩余积分和不可变 `code_role`。代理采用默认拒绝策略；后台生成的充值码必须标记为 `auto_topup`，主激活码与充值码不能混用，显式 `0` 积分不会回退到初始赠送值。

## 以后部署时的顺序

1. 备份授权数据库、Nginx 和现有服务。
2. 将本目录复制到服务器临时目录。
3. 执行 `sudo bash install.sh`（只安装，不启动）。
4. 编辑 `/etc/product-operation-report/proxy.env` 检查非敏感配置；模型 Key 使用下面的服务器密钥保险箱写入，不写进客户端、安装包或 GitHub。
5. 使用真实授权响应样本验证 `AUTHORIZATION_CONTRACT.md`，重点验证 `/device/status` 与 `/credits/consume`，再在回环地址测试 `/health`、`/session`、充值与扣费。
6. `install.sh` 会安装 Nginx 限流区和公共代理片段；将 `nginx-location.conf` 加入 `api.dadaozixun.com` 后执行 `nginx -t`。
7. `systemctl enable --now product-report-proxy`，再重载 Nginx。

不要把 `proxy.env`、`provider-keys.json`、方舟 Key、会话令牌或数据库复制回客户端或 GitHub Actions。

## 豆包 2.1 迁移

所有新请求统一使用 `doubao-seed-2-1-pro-260915`，Base URL 为
`https://ark.cn-beijing.volces.com/api/v3`。客户端仍连接自己的业务代理，使用短期设备会话；方舟 Key 只在服务器配置。

1. 在方舟控制台开通该模型；M4 对标研究还需要开通基础联网搜索。
2. 备份服务器配置和代理代码，然后部署本目录新版代码。安装脚本会安装 `provider_config.py` 到代理目录和密钥轮换工具旁；升级时不能漏掉它。
3. 检查现有 `/etc/product-operation-report/proxy.env`，将 `POR_PROVIDER_BASE_URL` 改为方舟地址，清空旧 `POR_PROVIDER_API_KEY`。安装脚本不会覆盖已有配置。真实 Key 用下方隐藏输入命令写入 `/etc/product-operation-report/provider-keys.json`。
4. `set` 命令会移除旧模型映射，保留旧供应商配置用于备份回滚。旧配置恢复需要同时回滚旧代理和客户端；不要直接给新代理加载只含旧模型映射的文件。
5. 代理代码/环境变量升级后需要重启 `product-report-proxy`；只轮换 Key 时无需重启。检查 `/health` 的 `models` 只有该豆包模型，且 `provider_keyring.models` 中对应线路已配置。
6. 配套发布本分支客户端后，再验证资料清洗、各模块、M4 搜索引用和结果确认后的积分结算。旧客户端请求旧模型会被新代理拒绝，因此升级窗口需要协调。仓库测试是离线验证，不能代替配置 Key 后的真实调用。

普通任务使用 `/chat/completions`，输出上限使用 `max_tokens`；清洗/摘要关闭深度思考。
M4 使用 `/responses`，启用深度思考和 `web_search`，最多一轮、每轮两个关键词；不发送原中转专用的搜索参数或 `prompt_cache_key`。

价格按[官方标准在线推理](https://docs.volcengine.com/docs/ark/model-pricing?lang=en&redirect=1)：输入 6 元/百万 token、输出 30 元/百万 token、命中缓存输入 1.2 元/百万 token。
豆包成本直接用人民币计算，不受 `POR_USD_CNY_RATE` 影响；保留历史模型价格仅用于历史记录结算，不开放旧模型请求。没有创建显式持久缓存，因而不计算按小时存储费。
联网资源默认按 4 元/千次计价，优先读取方舟返回的 `usage.tool_usage.web_search`，去重后的搜索调用事件作为兜底。服务器原有 `POR_WEB_SEARCH_USD_PER_CALL` 可覆盖默认值；免费额度或折扣应按账号实际成本调整。原积分倍率、失败零扣费、确认后结算和幂等规则保持不变。

接口参考：[鉴权与地址](https://docs.volcengine.com/docs/ark/base-url-and-authentication?lang=en)、[Responses](https://docs.volcengine.com/docs/ark/create-model-responses-api?lang=en)、[联网搜索](https://docs.volcengine.com/docs/ark/web-search?lang=en)。

## 模型 Key 无停机轮换

首次配置或更换 Key 时，在服务器执行（命令会隐藏输入，不把 Key 放进命令行历史或进程列表）：

```bash
sudo /usr/local/sbin/product-report-rotate-key set \
  --profile ark-doubao \
  --key-id 2026-10-a \
  --base-url https://ark.cn-beijing.volces.com/api/v3 \
  --models doubao-seed-2-1-pro-260915 \
  --activate
```

脚本会先用新 Key 做一个极小的真实请求验证，通过后才原子写入。运行中的代理会在下一次请求自动读取新版本，不需要重启；已经开始的请求继续使用它启动时取得的旧 Key。旧 Key 会保留为备用，如果新 Key 在建连时返回 401/403，代理会在尚未向用户输出内容前自动尝试备用 Key。

查看配置只显示标识，不显示密钥：

```bash
sudo /usr/local/sbin/product-report-rotate-key status
```

需要回滚时，将旧标识重新设为活动 Key：

```bash
sudo /usr/local/sbin/product-report-rotate-key activate --profile ark-doubao --key-id 2026-10-a
```

确认新 Key 稳定并等待至少 10 分钟（覆盖最长在途请求）后，再删除非活动旧 Key：

```bash
sudo /usr/local/sbin/product-report-rotate-key remove --profile ark-doubao --key-id OLD_NON_ACTIVE_KEY_ID
```

`provider-keys.json` 由服务账号独占读取，权限固定为 `0600`。文件损坏、写入中断或权限错误时，代理继续使用内存中的上一份有效配置，并在 `/health` 只报告安全的加载状态和备用数量，绝不返回 Key、Key 哈希或完整配置。

当前只开放一个豆包模型，可在同一方舟供应商配置中轮换多个 Key。旧 GPT/Claude 备用模型不会自动调用。代理仍保留上游模型名核验和成本审计。

代理每次创建会话和开始模型任务前都会用 `/device/status` 刷新授权服务器余额。模型返回有效内容后，代理使用本次实际模型请求唯一的 `request_id` 调用 `/credits/consume`；客户端传入的稳定 `billing_request_id` 只用于把自动重试和备用模型归到同一个逻辑任务。结算服务短暂不可用时保留预留并标记为待结算，下一次设备验证时仍用该次模型请求原来的 `request_id` 重试，确保同一笔金额只结算一次。

升级前已经因“同一逻辑 ID、不同金额”进入 `billing_pending` 的旧冲突记录不会再次扣费；代理会保留其供应商成本审计，标记为 `billing_conflict_released`，并只释放对应的预留积分。

代理重启时，尚未提交给上游的任务会释放预留；已经提交的任务会进入待结算状态，等设备重新连接后按同一任务 ID 完成保守结算，避免供应商已产生费用而客户端零扣费。

本地只读验证：`python -m unittest -v test_proxy.py`。
