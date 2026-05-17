# studybot - 智能做题 Agent

基于 nanobot 架构的轻量级 AI 做题助手，提供 Web UI 交互界面。

## 核心特性

| 特性 | 说明 |
|------|------|
| 💬 对话 | 流式输出聊天，支持多轮对话 |
| 📚 题库管理 | 上传 TXT/JSON/CSV/MD/PDF 等文件，AI 自动提取题目 |
| 📝 做题练习 | 题库选题 / 按难度筛选 / 按计划做题，AI 评价答案并打分 |
| 🧠 背题复习 | 基于间隔重复（SM-2）的卡片复习系统 |
| 📋 学习计划 | 选择题库 + 设定天数 + 每日题数，自动预分配题目，跟踪每日进度 |
| 🧠 记忆系统 | LLM 反思提炼经验，用户画像追踪，跨会话薄弱点针对性出题 |
| 📐 上下文压缩 | 长对话自动 LLM 增量摘要，降低 Token 消耗 |
| 📊 学习进度 | 统计做题量、正确率、连续天数、题库分布 |
| ⚙️ 设置 | 配置 API Key、Base URL、模型、主题 |

## 技术栈

- Python 3.10+
- 内置 HTTP 服务器 + WebSocket（零外部 Web 框架）
- OpenAI 兼容 API
- ReAct Agent 循环 + Tool Calling
- SM-2 间隔重复算法

## 安装

```bash
cd D:\project\studybot
pip install -e .
```

## 配置

编辑 `~/.studybot/config.json`:

```json
{
  "provider": {
    "api_key": "your-api-key",
    "api_base": "https://api.deepseek.com",
    "model": "deepseek-v4-flash"
  },
  "gateway": {
    "host": "127.0.0.1",
    "port": 8765
  },
  "streaming": true,
  "channels": ["web"]
}
```

## 启动

```bash
studybot
```

打开浏览器访问 http://127.0.0.1:8769

## 功能说明

### 💬 对话
- 在聊天窗口输入消息，AI 流式返回回答
- 支持拖拽或点击上传文件（TXT/PDF/MD/CSV/JSON 等）
- 上传的文件自动解析为题库
- 长对话自动触发上下文压缩，LLM 增量摘要旧消息

### 📚 题库管理
- 上传的文件自动提取 Q&A 题目
- 支持本地解析（CSV/Markdown/JSON/子弹列表）和 AI 解析（自然语言兜底）
- 查看每个题库的题目列表、领域标签
- 支持删除题库

### 📝 做题练习
- **按题库做题**：选择题库（多选）和难度（简单/中等/困难）筛选
- **按学习计划做题**：关联已创建计划，自动锁定题库和每日配额
- AI 生成题目或从题库选题，出题时参考用户薄弱领域
- 提交答案后 AI 评分（0-100）、给出反馈和疏漏点
- **反思提炼**：每次答题后 LLM 自动分析错误模式，提取经验入库
- 可一键加入背题列表

### 🧠 背题复习
- 基于 SM-2 间隔重复算法
- 每次复习按质量评分（1-5），自动调整复习间隔
- 显示待复习卡片数量和进度

### 📋 学习计划
- 创建计划：选择题库 + 设置总天数 + 每日题数
- 自动计算当前进行到第几天
- 今日任务面板显示已完成 / 剩余题数
- 从计划一键跳转到做题
- 日历格子直观展示每日完成状态

### 📊 学习进度
- 总做题数、正确率、题库数量、连续天数统计
- 各题库练习分布条形图
- 最近 20 条练习活动记录

### ⚙️ 设置
- 配置 API Key、Base URL、模型名称
- 飞书通道配置
- 主题切换（跟随系统 / 亮色 / 暗色）

## 项目结构

```
studybot/
├── studybot/
│   ├── gateway.py            # 入口：启动 Gateway
│   ├── session.py            # 会话管理 + 上下文压缩
│   ├── storage/
│   │   ├── __init__.py
│   │   └── db.py             # SQLite 持久化层
│   ├── bus/
│   │   └── __init__.py       # 消息总线
│   ├── providers/
│   │   ├── base.py           # LLM 提供者基类（含流式）
│   │   └── openai_compat.py  # OpenAI 兼容提供者
│   ├── channels/
│   │   ├── __init__.py
│   │   ├── base.py           # 通道基类
│   │   ├── websocket.py      # WebSocket 通道
│   │   ├── webui.py          # Web UI 通道（路由 + 启动 + SPA 模板）
│   │   ├── practice.py       # 出题、评分、文件解析引擎
│   │   ├── review.py         # SM-2 间隔重复复习管理
│   │   └── memory.py         # 记忆系统（反思、画像、经验）
│   ├── agent/
│   │   ├── loop.py           # Agent 循环（含上下文压缩）
│   │   ├── runner.py         # ReAct 流式执行器
│   │   └── tools/
│   │       ├── base.py       # Tool 抽象基类
│   │       ├── registry.py   # 工具注册与 schema 生成
│   │       └── practice.py   # 练习工具（10+ action 编排）
│   └── config/
│       └── __init__.py       # 配置
├── pyproject.toml
└── README.md
```

## 数据存储

```
~/.studybot/practice_data/
├── banks.json                # 题库数据
├── review_cards.json         # 背题卡片
├── plans.json                # 学习计划
└── memory.json               # 记忆系统（经验 + 用户画像）
```
