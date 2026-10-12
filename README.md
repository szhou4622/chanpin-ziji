# 产品内容策略系统（产品经营报告）

本仓库是产品经营报告后续开发的主仓库：<https://github.com/szhou4622/chanpin-ziji>。

初始基线为用户确认的 Windows 安装版 **1.2.0**，源码来自发布提交 `dc076234ed51e873fb3c02db504f5dafb749f177`。迁移保留桌面应用、内置报告规则、测试、打包配置及服务端源码，不包含本机密钥、激活记录、用户资料或安装包。

## 本地开发

使用 Node.js 22，在本仓库执行：

```bash
cd product-operation-report-app
npm ci
npm run dev
```

提交前执行：

```bash
npm run typecheck
npm run lint
npm run test:unit
npm run test:regression
npm run build
```

应用详细说明见 [应用 README](product-operation-report-app/README.md)，激活与更新说明见 [license-and-update.md](product-operation-report-app/docs/license-and-update.md)。`server-updates/` 保存服务端代码；正式服务配置和凭证需在部署环境单独提供。

## 自动检查与打包

推送主分支和提交 Pull Request 时执行源码检查。原有三平台安装包工作流已保留，通过手动运行或推送版本标签触发。macOS 签名、公证和服务器发布所需的 GitHub Secrets/Variables 需在本仓库单独配置；此次源码迁移不发布安装包或更新线上服务。

迁移来源及逐文件校验记录见 [源码迁移记录](docs/source-migration.json)。
