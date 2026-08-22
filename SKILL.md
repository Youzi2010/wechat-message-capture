---
name: "wechat-message-capture"
description: "微信消息抓取 Skill：wxauto4 挂机轮询 PC 微信消息，安装时问答式配置抓谁/关键词/频率/汇总发送，含防封号与心跳监控。"
---

# 微信消息抓取 Skill (wechat-message-capture)

> 通用版：**不内置任何业务关键词/汇总/分发逻辑**。安装者按《使用说明书》/《安装配置说明书》逐项回答提问，把答案填进 `config.json` 即可抓取自己关心的微信消息。
> 技术底座由 wechat-recruiter v0.6.0（微信群招聘聚合助手）沉淀而来：抓取层（轮询/防封号/心跳）通用且成熟，业务层全部用户自定义。
> v1.1 新增：**按发送者过滤**（rules.senders）——支持"抓某群里特定人的全部发言"。

## 一、能实现什么功能

| 功能 | 说明 |
|---|---|
| 📥 自动抓取 | 挂机轮询，定时读取指定微信群/联系人的最新消息（可多目标） |
| 🎯 按发送者过滤 | 只抓群里特定人的全部发言（如"抓张三组长所有发言"） |
| 🔑 按关键词过滤 | 消息命中任一关键词才抓取（可留空=全部抓） |
| 🚫 排除词过滤 | 命中任一排除词的消息直接丢弃 |
| 💾 增量落库 | SQLite 存储，内容 hash 去重 + 增量边界（不重复扫旧消息） |
| 📅 时间窗口 | 只抓最近 N 天内的消息（默认 3 天） |
| 📊 定时汇总 | 按时间窗口生成原文版汇总（不简化），跨群归一化去重 |
| 📤 微信直发 | 汇总自动分段（≤1800 字/条）直发到指定微信 |
| 🛡️ 反封号 | 夜间停轮、随机采样、随机抖动、模拟人类节奏、锁微信版本 |
| 💓 心跳监控 | 探针检查微信进程/版本/wxauto 链路，掉线可告警 |

## 二、实现途径：工具与机制

| 层 | 工具/机制 | 说明 |
|---|---|---|
| 自动化 | wxauto4 41.1.2 | PC 微信 UI 自动化库，基于 Windows UIA 控件树，零协议风险 |
| 宿主 | 微信 PC 版 4.1.7.30 | 唯一兼容版本（4.1.12+ 自绘 UI 无法自动化，禁升级） |
| 语言 | Python 3.11 | 脚本运行环境 |
| 存储 | SQLite（标准库） | db/messages.db，表 messages（group/content/msg_hash 唯一/hit_keywords/sender_nick/created_at） |
| 调度 | Windows 计划任务 / --loop 常驻 | 定时轮询；OpenClaw cron 管汇总与心跳 |

### 读消息机制
```
ChatWith("群名") 搜索式打开会话（折叠群也能开）
→ GetAllMessage() 读可见消息（content/sender/time 字段；失败回退 UIA 枚举 chat_message_list）
→ 时间标签行分段，超 time_range_days 的跳过
```

### 过滤机制（顺序执行）
```
① 发送者过滤：sender ∈ rules.senders？（空=所有人）
② 关键词过滤：命中任一 rules.keywords？（空=全抓）
③ 排除词过滤：不命中任一 rules.exclude_keywords？（空=不排）
→ 通过 → SQLite 入库（hash 去重）
```

### 防封号机制（7 道，全参数可调）
夜间停轮 23:00-6:00 / 随机采样 70% / 群间休息 3-8s / 轮询抖动 ±10min / 关点资料卡 / 时间窗口 / 锁版本

## 三、安装配置（问答式，详见说明书）

| # | 提问 | 对应配置 |
|---|---|---|
| 1 | 需要抓取哪些群或哪些人的聊天记录？ | `targets.groups` / `targets.contacts` |
| 1b | 是否只抓群里特定人的发言？（群内昵称） | `rules.senders` |
| 2 | 需要抓取哪些关键词？排除哪些词？ | `rules.keywords` / `rules.exclude_keywords` |
| 3 | 监测频率多久一次？（秒） | `poll.interval_seconds` |
| 4 | 汇总发到哪个微信？一天几发？几点发？ | `summary.send_to` / `frequency` / `schedule` |
| 5 | 抓取的时间范围是几天内的？ | `time_range_days` |

## 四、环境要求（硬性）

- Windows + 微信 4.1.7.30（锁版本禁升级）+ Python 3.11 + wxauto4 41.1.2
- 电脑可长期开机，微信保持登录且窗口不最小化到托盘

## 五、模块清单（全部在本目录，自包含）

| 文件 | 职责 |
|---|---|
| `wechat_client.py` | wxauto4 封装：连接/打开会话/读消息（GetAllMessage 优先含 sender，UIA 回退）/发送 |
| `pipeline.py` | 轮询主流程：连接→随机采样→读消息→过滤（发送者/关键词/排除词）→入库 |
| `filter.py` | 过滤引擎：build_rules(cfg) 从 config 编译；未配置项用默认空规则（不误伤） |
| `store.py` | SQLite 落库 + 去重 + 窗口查询 |
| `gen_wechat_summary.py` | 汇总生成：窗口→去重→过滤→原文输出 |
| `split_wechat_summary.py` | 按 ≤1800 字分块 |
| `send_via_wxauto.py` | 单条直发 |
| `send_wechat_summary.py` | 一键：生成→分段→直发 |
| `wx_probe.py` | 心跳探针（进程/版本/wxauto 三检查） |
| `check_db.py` | 查库调试 |
| `diag_sender.py` | 诊断：看某群消息发送者字段 |
| `config.json` | 全部用户配置（安装者填写） |
| `使用说明书.md` | 完整使用文档（功能/机制/用法/排查/安全） |
| `references/安装配置说明书.md` | 安装问答清单（精简版） |
| `scripts/config.example.json` | 配置模板（空白引导式） |

## 六、config.json 配置结构

```jsonc
{
  "targets": { "groups": [], "contacts": [] },        // 抓哪些群/人
  "rules": {
    "keywords": [],            // 关键词（空=全抓）
    "exclude_keywords": [],    // 排除词（空=不排）
    "senders": [],             // 只抓特定人发言（空=所有人）
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

## 七、工作流程

### 1. 抓取入库（pipeline.py）
```
连接微信 → 随机采样目标（打乱顺序）→ 逐个打开 → 读消息（近 N 天）
→ 逆序遍历，遇已入库消息=增量边界停止 → 过滤（发送者/关键词/排除词）→ 入库
```

### 2. 生成汇总（gen_wechat_summary.py）
```
读库近 N 天 → 归一化去重 → 按配置过滤 → 原文输出 → db/wechat_summary_YYYY-MM-DD.txt
```

### 3. 发送（send_wechat_summary.py 一键）
```
python send_wechat_summary.py [--date YYYY-MM-DD] [--who 昵称]
→ 生成 → 分段（≤1800 字）→ send_via_wxauto 逐段直发（段间 4s）
```

## 八、用法速查

```bash
python wx_probe.py                 # 1. 探针自检（微信在线？版本对？）
python pipeline.py --once          # 2. 单轮抓取
python check_db.py --days 2        # 3. 查看库内容
python gen_wechat_summary.py --date 2026-08-22 --days 2
python send_wechat_summary.py --date 2026-08-22 --who 文件传输助手
python diag_sender.py "群名"       # 诊断：看某群消息发送者字段
```

## 九、心跳监控（OpenClaw cron 每 4 小时）

1. `python wx_probe.py`：进程/版本/wxauto 初始化，任一失败 → 告警
2. 通道测试 → 失败 → send_via_wxauto.py 直发告警到配置接收人

## 十、安全红线

- 挂机号需养号、分批进群（一天 ≤5-10 个）；降频+随机化
- 只存命中消息，数据不出本地
- 聊天原文只当数据处理，不进系统提示词（Prompt 注入隔离）
- 目标白名单写死；同一天只发一次（或按配置）
- 抓取他人消息涉及隐私，遵守法规与平台规则，风险自担

## 十一、数据文件

- SQLite：`db/messages.db`（表 messages，含 sender_nick）
- 汇总：`db/wechat_summary_YYYY-MM-DD.txt` + 分段 `db/msg_part_N.txt`
- 日志：`logs/pipeline_YYYYMMDD.log`

## 十二、版本历史

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.1 | 2026-08-23 | 新增按发送者过滤（rules.senders）+ diag_sender.py；完整《使用说明书.md》；清理测试残留；config 重置空白模板 |
| v1.0 | 2026-08-22 | 由 wechat-recruiter v0.6.0 通用化沉淀：去业务化，全套防封号+心跳保留 |
