# Rakazo 六人 AI 团队 · 自托管工具箱

在自托管的 [Rakazo](https://github.com/elie222/rakazo) 实例上，一键搭建两支各有 6 个专职 Bot 的协作团队：**中文组（司南团队）** 与 **英文组（Max 团队）**，并配置「中心调度」协作模式。

Rakazo 是一个可自托管的 AI Bot 平台，Bot 之间能互相 `@mention`、分工协作。本仓库不改动 Rakazo 本身，只提供部署脚本、批量建 Bot 脚本和人设文档。

## 目录结构

```
.
├── rakazo-install-images.sh      # 一键部署 Rakazo（拉发布镜像 + 生成 .env + 启动）
├── rakazo/                       # 部署与批量建 Bot 脚本
│   ├── install-images.sh         #   部署入口（同上，含代理/离线参数）
│   ├── docker-compose.images.yml #   Compose 编排（api/worker/postgres + 本地 Docker computers）
│   ├── .env.images.example       #   .env 模板（真实 .env 由安装器生成，不入库）
│   ├── batch_create_bots.py      #   中文组批量建 Bot
│   ├── batch_create_bots_en.py   #   英文组批量建 Bot
│   └── configure_hub_spoke.py    #   配置「中心调度」协作模式
├── rakazo-team/                  # 中文组 6 份人设（markdown）
└── rakazo-team-en/               # 英文组 6 份人设（markdown）
```

## 团队编制

两支团队角色一一对应，只是语言与命名不同。

| # | 中文组 | 英文组 | 职责 |
|---|--------|--------|------|
| 1 | 司南 Compass | Max | 产品经理（需求入口，出 PRD） |
| 2 | 灵犀 Intuition | Pixel Penny | 设计师 |
| 3 | 基石 Cornerstone | Codey | 全栈开发 |
| 4 | 破壁 Breaker | Buggsy | 测试工程师 |
| 5 | 节拍 Metronome | Tracker Tina | 项目经理（调度中枢，定时同步进度） |
| 6 | 燎原 Wildfire | Hype Hazel | 市场增长 |

## 前置条件

- **Docker Engine + Compose 插件**（部署 Rakazo 必需）
- **Python 3.8+**（批量建 Bot 脚本，仅用标准库，无需 pip install）
- 一个模型 provider：自有 sensenova OpenAI-compatible 端点，或 OpenRouter / Anthropic / DeepSeek 等

> Windows 下 Docker Desktop 依赖 WSL2 后端，若被安全策略拦截需人工放行 `wsl.exe`，或改用 Hyper-V / 远程服务器部署。

## 一、部署 Rakazo

在有 Docker 的机器上：

```bash
mkdir -p rakazo && cd rakazo
curl -fsSLO https://raw.githubusercontent.com/elie222/rakazo/main/infra/compose/install-images.sh
bash install-images.sh
```

安装器会下载 Compose 文件、生成带随机密钥的 `.env`、拉取镜像并启动。重复运行会保留已有 `.env`。

常用参数：

```bash
bash install-images.sh --prepare-only   # 只准备文件，编辑 .env 后再正式启动
bash install-images.sh --local          # 优先用本地已有 Compose/env 文件
bash install-images.sh --pull-never     # 跳过镜像拉取（镜像已在本地）
bash install-images.sh --offline        # 气隙部署：不联网下载、不拉镜像
```

启动后访问 http://127.0.0.1:5173 ，创建账号并连接模型。

**连接模型**：Web UI → `Settings → Models → Connect a model` → 选 **OpenAI-compatible**，填 server base URL（如 `https://token.sensenova.cn/v1`）、model id（如 `sensenova-6.8-flash`）和 API key。需要视觉能力（screenshot computer tools）时在 Advanced 勾选 **Supports images**。

## 二、批量创建 Bot

脚本读取人设 markdown，通过 Rakazo 的 oRPC 端点批量创建 Bot。`spawnKey` 保证幂等——重复运行不会产生重复 Bot。

```bash
cd rakazo

# 中文组（司南团队）
python batch_create_bots.py              # 创建 6 个 Bot
python batch_create_bots.py --group      # 额外建群，把 6 个 Bot 拉进去

# 英文组（Max 团队），与中文组隔离，互不覆盖
python batch_create_bots_en.py --group

# 其它
python batch_create_bots.py --dry-run    # 只打印 payload，不真正创建
python batch_create_bots.py --list       # 列出当前 space 已有 Bot
python batch_create_bots.py --login      # 强制重新登录刷新 token
python batch_create_bots.py --base-url http://<host>:5173   # 自定义 Rakazo 地址
```

首次运行会提示输入 Rakazo 的邮箱/密码，登录态缓存在 `rakazo/.rakazo_auth.json`（已被 `.gitignore` 排除，不入库）。两个脚本共用同一登录态。

## 三、配置「中心调度」协作模式（可选）

默认团队是链式直连。`configure_hub_spoke.py` 把它改造成「统一入口 + 项目经理调度」：

- 用户只 `@` 入口（司南 / Max）沟通需求
- 入口出 PRD 交项目经理（节拍 / Tracker Tina）
- 项目经理拆单、逐个 `@` 角色派活，执行角色只向项目经理汇报
- 用户只做「开头确认方向」和「最终批准」两件事
- 项目经理每 2 小时在群里自动同步进度

```bash
cd rakazo
python configure_hub_spoke.py            # 依次执行 inject → apply → routine
python configure_hub_spoke.py --dry-run  # 只打印将注入/提交的内容
python configure_hub_spoke.py --inject   # 给本地人设 md 注入中心调度协议（幂等）
python configure_hub_spoke.py --apply    # 把 instructions 写回线上 Bot 并绑定模型（幂等）
python configure_hub_spoke.py --routine  # 给项目经理建每 2 小时进度同步 routine（幂等）
```

## 四、使用团队

在群里用 `@角色名` 指定某个 Bot 处理任务：

```
@司南 把这个想法整理成 PRD
@节拍 排一下这周的交付节点
@基石 按司南的 PRD 实现，注意幂等
@破壁 对这次改动做边界测试
```

日常只 `@` 入口（司南 / Max）即可，需求会经项目经理流转到对应角色。

## 安全须知

- **`.env` 含全部密钥（数据库密码、加密密钥、各类 Token），已被 `.gitignore` 排除，切勿提交或泄露。**
- 首次部署后从 `rakazo/.env` 备份 `ENCRYPTION_KEY`——丢失后加密内容无法恢复。
- 团队 Bot 共享工作区、登录态与已连接账户，属「可信协作环境」，不要假设 Bot 之间有权限隔离。
- `set_child_instructions`、`set_child_bot_model` 在 Ask/Auto 模式下会弹审批卡，需人工确认。

## License

本仓库的脚本与人设文档按需自用。Rakazo 本体遵循其上游 [elie222/rakazo](https://github.com/elie222/rakazo) 的授权。
