<div align="center">

# 星轨 Orbit

### AI Agent 端到端系统 — 让 AI 自主完成从需求到交付的全流程

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=next.js&logoColor=white)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-vector_store-6B6BFF)](https://www.trychroma.com/)

</div>

---

## 项目简介

**星轨（Orbit）** 是一套面向中小微企业和个人用户的 AI Agent 端到端系统，让用户只需描述"想做什么"，AI 即可自主完成 **需求对齐 → 规划 → 编码 → 审查 → 交付** 的全流程闭环。

核心能力：

- **RAG 知识库**：上传文档 → 语义切割 → 向量化存储 → 语义检索 → LLM 生成带引用回答（SSE 流式输出）
- **多租户隔离**：每个用户拥有独立知识库 collection，数据互不可见（JWT + bcrypt）
- **模型路由**：三层混合路由（规则引擎 → 语义路由 → LLM 分类），按问题复杂度自动选择模型档位
- **语义缓存**：相同/相似查询直接命中缓存，避免重复调用 LLM
- **Agent Loop**：五 Agent 协作编排框架，通过文件协议跨会话持久化

---

## 架构总览

```
┌─────────────────────────────────────────────────────┐
│              Next.js Frontend (port 3000)            │
│   Chat UI  │ 知识库面板 │ Agent 观察台 │ 设置/策略    │
├─────────────────────────────────────────────────────┤
│               FastAPI Backend (port 8001)            │
│   RAG 检索  │  LLM 生成  │  SSE 流式  │  多租户     │
├─────────────────────────────────────────────────────┤
│                   数据层                             │
│   ChromaDB (向量)  │  SQLite  │  文件存储           │
├─────────────────────────────────────────────────────┤
│                 Agent Loop                           │
│   Master → Planner → Builder → Reviewer → User      │
│   (文件通信协议 + 迭代熔断 + 分支安全)               │
└─────────────────────────────────────────────────────┘
```

---

## 目录结构

```
Orbit/
├── frontend/                  # Web UI (Next.js 16 + Tailwind v4)
│   ├── src/app/               # 路由 + 全局样式
│   ├── src/lib/               # API 封装 + 工具函数
│   └── src/components/        # UI 组件
│       ├── chat/              # 流式对话、Markdown、引用悬浮
│       ├── sidebar/           # 响应式侧边栏
│       ├── knowledge-base/    # 文档上传、列表管理
│       ├── search/            # 语义搜索面板
│       ├── agent/             # Agent 观察台
│       ├── strategy/          # RAG 策略配置
│       ├── settings/          # API Key + 多模型管理
│       ├── onboarding/        # 新手引导
│       └── auth/              # 登录/注册
│
├── backend/                   # 知识库后端 (FastAPI)
│   └── app/
│       ├── main.py            # 30+ API 端点
│       ├── api/               # 路由域（knowledge/auth/memory/storage...）
│       ├── llm/               # 公共 LLM 客户端（配置/请求/Prompt）
│       ├── generate/          # LLM 生成（非流式）
│       ├── stream/            # SSE 流式输出（7 阶段事件）
│       ├── search/            # 语义检索
│       ├── embed/             # 双后端 Embedding
│       ├── chunk/             # 语义切割（中文适配）
│       ├── ingest/            # 文件解析 (PDF/MD/TXT)
│       ├── store/             # ChromaDB 存储
│       ├── router/            # 模型路由 (fast/balanced/strong)
│       ├── cache/             # 语义缓存
│       ├── multitenant/       # 多租户隔离
│       ├── memory/            # 长期记忆
│       ├── middleware/        # JWT 鉴权 + X-Request-ID
│       └── schemas/           # Pydantic 模型
│
├── agent-loop/                # Agent 编排框架
│   ├── agents/                # Agent 角色定义
│   ├── memory/                # Agent 运行时状态
│   ├── scenes/                # 场景定义
│   └── skills/                # 集成 Skill
│
└── data/                      # 运行时数据 (gitignore)
    ├── chroma_db/             # ChromaDB 向量存储
    ├── uploads/               # 上传文档
    └── logs/                  # 后端日志
```

---

## 快速开始

### 1. 启动后端

```bash
cd backend
pip install -r requirements.txt
python3 -m uvicorn app.main:app --port 8001 --host 0.0.0.0
```

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev -- -p 3000
```

### 3. 配置 API Key

打开 `http://localhost:3000` → 完成新手引导 → 左侧 **设置** → 展开模型卡片 → 填入 API Key 和模型名。

> API Key 仅保存在浏览器本地，前端通过 `X-API-Key` 请求头传递给后端，后端据此调用 LLM。

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LLM_API_KEY` | 空 | LLM Bearer 凭据 |
| `LLM_BASE_URL` | `https://api.openai.com/v1/chat/completions` | OpenAI-compatible Chat Completions 地址 |
| `LLM_MODEL` | `gpt-4o-mini` | 默认模型 |

### 4. 上传文档并对话

- 左侧 **知识库** → 拖拽上传 PDF/MD/TXT
- 左侧 **对话** → 输入问题，AI 基于知识库检索 + LLM 生成回答
- 回复中的文件名可 hover 查看原文引用片段

---

## API 端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/health` | GET | 深度健康检查 |
| `/api/knowledge/upload` | POST | 上传文件并索引 |
| `/api/knowledge/search` | GET | 语义搜索 |
| `/api/knowledge/ask` | POST | RAG 问答 |
| `/api/knowledge/ask/stream` | GET | SSE 流式问答 |
| `/api/knowledge/strategy` | GET/PATCH | RAG 策略管理 |
| `/api/knowledge/logos` | POST | 对话总结 |
| `/api/auth/register` | POST | 注册 (限流) |
| `/api/auth/login` | POST | 登录 (限流) |

---

## Agent Loop

五 Agent 通过 markdown 文件通信，跨 session 持久化：

| Agent | 职责 | 权限 |
|-------|------|------|
| **Master** | 需求对齐，大白话 → 结构化 Spec | 一次性 |
| **Planner** | 产出执行计划 + 影响面分析 | 只读 |
| **Builder** | 按计划执行代码修改 | 可读写 |
| **Reviewer** | 两阶段审查 (Spec + Quality) | 只读 |
| **User Agent** | UX 截图审查 (前端/全栈场景) | 只读 |

---

## 技术栈

| 层 | 技术 |
|---|------|
| 前端框架 | Next.js 16 + TypeScript |
| 样式 | Tailwind v4 + CSS 变量 |
| 后端框架 | FastAPI + Python 3.9+ |
| 向量数据库 | ChromaDB (HNSW + cosine) |
| 关系数据库 | SQLite |
| Embedding | sentence-transformers (MiniLM) |
| 文件解析 | PyPDF2 |
| 流式输出 | SSE |
| Agent 框架 | 自研五 Agent + 文件通信协议 |

---

## License

MIT
