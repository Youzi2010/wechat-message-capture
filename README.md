# 📥 WeChat Message Capture (微信消息抓取)

> 基于 wxauto4 的 PC 微信消息抓取 Skill —— 挂机轮询指定微信群/联系人的消息，按你的规则过滤落库，定时汇总直发微信。**不内置任何业务逻辑**，安装时按问答配置即可抓取你关心的消息。

由微信群招聘聚合助手（wechat-recruiter v0.6.0）沉淀通用化而来：抓取层（轮询/防封号/心跳）成熟稳定，业务层完全由你自定义。

## ✨ 功能特性

| 功能 | 说明 |
|---|---|
| 📥 自动抓取 | 挂机轮询，定时读取指定微信群/联系人的最新消息（支持多目标） |
| 🎯 按发送者过滤 | 只抓群里特定人的全部发言（如"抓张三组长所有发言"） |
| 🔑 关键词过滤 | 消息命中任一关键词才抓取（留空 = 全部抓） |
| 🚫 排除词过滤 | 命中任一排除词的消息直接丢弃 |
| 💾 增量落库 | SQLite 存储，内容 hash 去重 + 增量边界（不重复扫旧消息） |
| 📅 时间窗口 | 只抓最近 N 天内的消息（默认 3 天） |
| 📊 定时汇总 | 按时间窗口生成原文版汇总（不简化），跨群归一化去重 |
| 📤 微信直发 | 汇总自动分段（≤1800 字/条）直发到指定微信 |
| 🛡️ 反封号 | 夜间停轮、随机采样、随机抖动、模拟人类节奏、锁微信版本 |
| 💓 心跳监控 | 探针检查微信进程/版本/wxauto 链路，掉线可告警 |

## 🧩 工作原理

```
┌─────────────┐   ChatWith(群名) 搜索式打开会话（折叠群也能开）
│  PC 微信     │ ──► GetAllMessage() 读可见消息（content/sender/time）
│  4.1.7.30   │       失败回退 UIA 枚举 chat_message_list
└──────┬──────┘
       │ 时间标签行分段，超 time_range_days 跳过
       ▼
┌─────────────┐   过滤顺序（可配置，全部可空）：
│  过滤引擎    │   ① 发送者 ∈ rules.senders？（空 = 所有人）
└──────┬──────┘   ② 命中任一 rules.keywords？（空 = 全抓）
       │          ③ 不命中任一 exclude_keywords？（空 = 不排）
       ▼
┌─────────────┐
│  SQLite 入库 │   db/messages.db，hash 去重
└─────────────┘
```

## 🔧 环境要求（硬性）

- **Windows** 10/11
- **微信 PC 版 4.1.7.30**（唯一兼容版本，4.1.12+ 自绘 UI 无法自动化，**禁止升级微信**）
- **Python 3.11** + **wxauto4 41.1.2**
- 电脑可长期开机，微信保持登录且窗口不最小化到托盘

```bash
pip install wxauto==4.1.1.2
```

## 📦 安装配置（问答式，约 2 分钟）

复制 `scripts/config.example.json` 为 `config.json`，按下面提问逐项填写：

| # | 提问 | 对应配置 |
|---|---|---|
| 1 | 需要抓取哪些群或哪些人的聊天记录？ | `targets.groups` / `targets.contacts` |
| 1b | 是否只抓群里特定人的发言？（群内昵称） | `rules.senders` |
| 2 | 需要抓取哪些关键词？排除哪些词？ | `rules.keywords` / `rules.exclude_keywords` |
| 3 | 监测频率多久一次？（秒） | `poll.interval_seconds` |
| 4 | 汇总发到哪个微信？一天几发？几点发？ | `summary.send_to` / `frequency` / `schedule` |
| 5 | 抓取的时间范围是几天内的？ | `time_range_days` |

详细安装问答清单见 [references/安装配置说明书.md](references/安装配置说明书.md)，完整使用文档见 [使用说明书.md](使用说明书.md)。

## 🚀 快速开始

```bash
python wx_probe.py                 # 1. 探针自检（微信在线？版本对？）
python pipeline.py --once          # 2. 单轮抓取
python check_db.py --days 2        # 3. 查看库内容
python gen_wechat_summary.py --date 2026-08-22 --days 2   # 4. 生成汇总
python send_wechat_summary.py --date 2026-08-22 --who 文件传输助手  # 5. 一键生成+分段+直发
python diag_sender.py "群名"       # 诊断：查看某群消息发送者字段
```

### 定时调度

- **轮询抓取**：`python pipeline.py --loop` 常驻，或 Windows 计划任务定时跑 `--once`
- **汇总发送**：配合 OpenClaw cron / 计划任务，每天定时跑 `send_wechat_summary.py`
- **心跳监控**：每 4 小时跑 `wx_probe.py`，失败即告警

## ⚙️ config.json 结构

```jsonc
{
  "targets": { "groups": [], "contacts": [] },        // 抓哪些群/人
  "rules": {
    "keywords": [],            // 关键词（空 = 全抓）
    "exclude_keywords": [],    // 排除词（空 = 不排）
    "senders": [],             // 只抓特定人发言（空 = 所有人）
    "require_phone": false     // 汇总是否必须带手机号
  },
  "time_range_days": 3,        // 抓几天内
  "poll": {
    "interval_seconds": 3600,  // 监测频率（秒）
    "jitter_seconds": 600,     // 轮询抖动（防封号）
    "sample_ratio": 0.7,       // 随机采样（防封号）
    "night_stop": { "start": 23, "end": 6 }  // 夜间停轮（防封号）
  },
  "summary": {
    "enabled": true,           // 是否汇总发送
    "frequency": "daily",      // 一天一发/多发
    "schedule": "20:00",       // 几点发
    "send_to": "文件传输助手", // 发到哪个微信
    "max_chars": 1800          // 单条上限（自动分段）
  },
  "db_path": "db/messages.db",
  "log_dir": "logs"
}
```

## 🛡️ 防封号机制（7 道，全参数可调）

1. **夜间停轮** 23:00–6:00 不抓取
2. **随机采样** 每轮只处理 70% 目标（默认），不固定规律
3. **群间休息** 3–8 秒随机间隔
4. **轮询抖动** ±10 分钟随机化触发时间
5. **关闭点资料卡** 不触发风控操作
6. **时间窗口** 只读最近 N 天消息，减少无效扫描
7. **锁微信版本** 4.1.7.30（新版本无法自动化，天然防误升级）

## 📁 项目结构

```
wechat-message-capture/
├── wechat_client.py          # wxauto4 封装：连接/打开会话/读消息/发送
├── pipeline.py               # 轮询主流程：连接→采样→读消息→过滤→入库
├── filter.py                 # 过滤引擎（发送者/关键词/排除词）
├── store.py                  # SQLite 落库 + 去重 + 窗口查询
├── gen_wechat_summary.py     # 汇总生成（原文输出）
├── split_wechat_summary.py   # 按 ≤1800 字分块
├── send_via_wxauto.py        # 单条直发
├── send_wechat_summary.py    # 一键：生成→分段→直发
├── wx_probe.py               # 心跳探针（进程/版本/wxauto 三检查）
├── check_db.py               # 查库调试
├── diag_sender.py            # 诊断：查看某群消息发送者字段
├── config.json               # 全部用户配置（安装者填写）
├── 使用说明书.md              # 完整使用文档
└── references/
    ├── 安装配置说明书.md       # 安装问答清单
    └── config.example.json   # 配置模板（空白引导式）
```

## ⚠️ 安全与合规

- 挂机号需养号、分批进群（一天 ≤5–10 个）；降频 + 随机化
- 只存命中消息，**数据不出本地**
- 聊天原文只当数据处理，不进系统提示词（Prompt 注入隔离）
- 目标白名单写死；同一天只发一次（或按配置）
- **抓取他人消息涉及隐私，请遵守当地法律法规与平台规则，风险自担**

## 📜 版本历史

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.1 | 2026-08-23 | 新增按发送者过滤（rules.senders）+ diag_sender.py；完整《使用说明书.md》；config 重置空白模板 |
| v1.0 | 2026-08-22 | 由 wechat-recruiter v0.6.0 通用化沉淀：去业务化，全套防封号 + 心跳保留 |

## 📬 反馈

问题或建议请提 [Issue](https://github.com/Youzi2010/wechat-message-capture/issues) 或 PR。
