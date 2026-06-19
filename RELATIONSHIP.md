# Free-Model-Hub 与 AI Programs Hub（AiOnAll）的关系

> 最后更新：2026-06-19

## 概述

[`D:\Free-Model-Hub`](docs/project-overview.md)（本目录）与 [`D:\AiOnAll`](D:\AiOnAll\ai-programs-browser.html) 是两个独立但互补的项目，共同构成一个完整的 AI 工具链生态系统。

---

## Free-Model-Hub（本仓库）— 模型中心

**定位**：后端 API 代理 / 免费 AI 模型聚合服务平台

**核心模块**：

| 模块 | 作用 |
|------|------|
| [`backend/scrapers/`](backend/scrapers/base.py) | 数十个模型提供商的抓取器（OpenRouter、Gemini、Groq、Cohere、NVIDIA 等） |
| [`backend/api/`](backend/api/__init__.py) | 统一的 RESTful API 接口 |
| [`backend/main.py`](backend/main.py) | 后端服务入口 |
| [`backend/scheduler.py`](backend/scheduler.py) | 抓取任务调度器 |
| [`backend/database.py`](backend/database.py) | 数据持久化存储 |
| [`backend/models/`](backend/models/__init__.py) | 数据模型与仓库 |

**核心功能**：
- 自动从多个提供商抓取免费 AI 模型信息
- 通过统一 API 暴露模型数据供客户端调用
- 定时调度抓取任务，保持数据更新

---

## AI Programs Hub — 程序中心

**位置**：[`D:\AiOnAll`](D:\AiOnAll\ai-launcher.py)

**定位**：桌面应用程序启动器 / 快捷方式管理中心

**核心文件**：

| 文件 | 作用 |
|------|------|
| `ai-launcher.py` | Python HTTP 服务器（端口 `18923`），提供程序启动、任务管理 API |
| `ai-programs-browser.html` | 前端浏览器界面，分类展示可启动的程序 |
| `programs.json` | 程序清单，记录各类 AI 工具的名称、路径、类型 |
| `start-web-hub.bat` | 一键启动脚本 |

**核心功能**：
- 在 Web 界面中分类展示用户电脑上所有 AI 相关软件
- 一键启动本地程序（桌面应用、便携版、CLI 工具、API 代理等）

---

## 两者的关系

### 维度对比

| 维度 | Free-Model-Hub（模型中心） | AiOnAll（程序中心） |
|------|--------------------------|-------------------|
| **定位** | **后端服务/API 层** | **工具管理/启动层** |
| **解决的核心问题** | 聚合免费 AI 模型，提供统一 API 接口 | 帮用户快速找到并启动各种 AI 桌面软件 |
| **用户交互方式** | 后端服务，通常由程序/API 调用 | 用户通过浏览器点击图标启动本地程序 |
| **技术栈** | Python 后端 + 爬虫 + 数据库 | Python HTTP Server + HTML/JS 前端 |
| **工作流角色** | 服务提供者（Service Provider） | 启动器（Launcher） |

### 协同工作流

```
用户 ──→ AI Programs Hub（启动器）
              │
              ├── 启动 Free-Model-Hub 后端服务
              ├── 启动客户端工具（Chat2API、9Router 等）
              │         │
              │         └── 调用 Free-Model-Hub API
              │                    │
              │                    └── 返回模型数据
              │
              └── 直接访问模型提供商的桌面客户端（Claude 等）
```

**三者形成完整工具链**：**启动管理（AiOnAll）→ API 代理（Free-Model-Hub）→ AI 客户端工具**
