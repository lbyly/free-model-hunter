# Free-Model-Hub × Hermes 集成可行性研究

> 研究日期: 2026-06-07
> 分支: `research/hermes-integration`

## 一、项目概览

### 1.1 Free-Model-Hub

**定位**：免费 AI 模型聚合与发现平台

- **技术栈**：FastAPI + SQLite + Python 爬虫
- **核心功能**：从 20+ 提供商抓取免费模型 → 自动分类(Tier 1/2/3) → 提供 REST API 搜索/筛选
- **数据模型**：
  - `providers` 表：`id, name, slug, website, scrape_url, scraper_class, is_active, hidden, logo_url`
  - `models` 表：`id, provider_id, model_id, name, type, capability_tier, use_case, is_free, context_window, tags, rate_limits`
- **API 端点**：
  - `GET /api/models` — 多维筛选模型列表
  - `GET /api/providers` — 获取所有提供商
  - `GET /api/classify/stats` — 分类统计

### 1.2 Hermes

**定位**：AI 命令行代理工具（类似 Claude CLI / Code CLI）

- **配置文件**：`~/.hermes/config.yaml` (696 行)
- **核心配置结构**：

```yaml
# 当前默认模型
model:
  default: sensenova-6.7-flash-lite
  provider: custom
  base_url: https://token.sensenova.cn/v1
  api_key: sk-xxx

# 后备提供商（按优先级排列）
fallback_providers:
  - provider: Omnirouter
    models: [free-stack]
  - provider: Cpamc
    context_length: 1000000
    models: [gemini-3.5-flash, ...]

# 自定义提供商（OpenAI 兼容端点）
custom_providers:
  - name: Cpamc
    base_url: http://127.0.0.1:8317/v1
    api_key: sk-xxx
    model: gemini-3.1-flash-lite
    models:
      gemini-3.5-flash:
        context_length: 1048576
      deepseek-v3.2:
        context_length: 131072
```

---

## 二、集成可行性分析

### ✅ 核心结论：**可行**

Free-Model-Hub 的数据可以自动生成 Hermes 的 `custom_providers` 配置，实现模型的自动发现与配置同步。

### 2.1 数据映射关系

| Free-Model-Hub 字段 | Hermes 配置字段 | 映射方式 | 备注 |
|---|---|---|---|
| `provider.name` | `custom_providers[].name` | 直接映射 | 提供商名称 |
| `provider.slug` | — | 作为唯一标识 | 用于 API Key 查找 |
| `provider.api_key` | `custom_providers[].api_key` | 从 `.env` 读取 | 已通过 `config.get_api_key_for_slug()` 获取 |
| `provider.scrape_url` | `custom_providers[].base_url` | 推导映射 | URL 需转为 `/v1` 格式的 API 端点 |
| `model.model_id` | `custom_providers[].models.{key}` | 直接映射 | 模型 ID |
| `model.context_window` | `custom_providers[].models.{key}.context_length` | 直接映射 | 上下文长度 |
| `provider.name` | `fallback_providers[].provider` | 直接映射 | 后备提供商 |

### 2.2 需要解决的问题

#### ❓ 问题 1：base_url 推导

Free-Model-Hub 的 `providers.scrape_url` 是**爬虫入口 URL**（如 `https://api.deepseek.com/v1`），而 Hermes 需要的是 **OpenAI 兼容的 chat completions 端点**。

**解决思路**：
- 部分爬虫已在 [`base.py`](backend/scrapers/base.py:48-49) 定义了 `chat_endpoint_base` 属性
- 可以扩展 `providers` 表增加 `api_base_url` 字段，或从 scrape_url 推导
- OpenRouter 格式：`https://api.deepseek.com/v1/chat/completions`

#### ❓ 问题 2：模型数量管理

Free-Model-Hub 管理的模型数量可能很大（几百个），而 Hermes 只需要**常用的、验证可用的免费模型**。

**解决思路**：
- 按 `capability_tier` 过滤：只导出 Tier 1（旗舰级）和 Tier 2（增强级）
- 按 `is_free=true` 过滤
- 按 `status=active` 过滤
- 允许用户在 UI 中选择要同步到 Hermes 的提供商

#### ❓ 问题 3：配置同步机制

Hermes 的配置是本地 YAML 文件，需要一种方式将 Free-Model-Hub 的数据推送到 Hermes 配置中。

**解决思路（多种方案）**：

| 方案 | 优点 | 缺点 |
|---|---|---|
| **A. Hermes Model Catalog API** | 标准方式，Hemes 原生支持 | 需要运行 Free-Model-Hub 后端 |
| **B. 导出脚本** | 零依赖，可离线使用 | 手动执行 |
| **C. Hermes 插件** | 自动同步，体验最佳 | 需要开发 Hermes 插件 |

---

## 三、推荐集成方案

### 方案 A：Hermes Model Catalog（推荐）

Hermes 的 [`model_catalog`](C:/Users/Administrator/.hermes/config.yaml:503-507) 配置段支持从远程 URL 获取模型目录：

```yaml
model_catalog:
  enabled: true
  url: https://hermes-agent.nousresearch.com/docs/api/model-catalog.json
  ttl_hours: 1
  providers: {}
```

**Free-Model-Hub 可以做**：新增 `/api/hermes/catalog` 端点，返回 Hermes 格式的 catalog JSON：

```json
{
  "providers": [
    {
      "name": "Groq",
      "baseUrl": "https://api.groq.com/openai/v1",
      "apiKeyEnv": "GROQ_API_KEY",
      "models": [
        {
          "id": "llama-3.3-70b-versatile",
          "contextLength": 131072,
          "type": "chat"
        }
      ]
    }
  ]
}
```

### 方案 B：配置导出脚本（最轻量）

新增一个 Python 脚本 `export_hermes_config.py`，从 Free-Model-Hub 的数据库读取数据，直接生成 Hermes 的 `config.yaml` 追加内容。

### 方案 C：Hermes 插件（最深度）

在 Hermes 的 `~/.hermes/plugins/` 或 `~/.hermes/hermes-agent/` 目录下开发一个插件，定期从 Free-Model-Hub 的 REST API 拉取最新模型数据，自动更新 `custom_providers` 配置。

---

## 四、示例输出

以下是根据 Free-Model-Hub 当前数据生成的 Hermes 配置示例：

```yaml
# 由 Free-Model-Hub 自动生成 - 不要手动编辑
custom_providers:
  - name: Groq
    base_url: https://api.groq.com/openai/v1
    api_key: ${GROQ_API_KEY}
    models:
      llama-3.3-70b-versatile:
        context_length: 131072
      mixtral-8x7b-32768:
        context_length: 32768

  - name: Google Gemini
    base_url: https://generativelanguage.googleapis.com/v1beta
    api_key: ${GEMINI_API_KEY}
    models:
      gemini-2.0-flash:
        context_length: 1048576
      gemini-2.0-flash-lite:
        context_length: 1048576

fallback_providers:
  - provider: Groq
    models:
      - llama-3.3-70b-versatile
      - mixtral-8x7b-32768
  - provider: Google Gemini
    context_length: 1048576
    models:
      - gemini-2.0-flash
```

---

## 五、实施路线图

| 阶段 | 任务 | 预估工时 |
|---|---|---|
| **Phase 1** | 新增 `/api/hermes/catalog` 端点，输出 Hermes 格式的模型目录 | 1-2 天 |
| **Phase 2** | 编写 `export_hermes_config.py` 导出脚本，一键生成 YAML 配置片段 | 0.5 天 |
| **Phase 3** | 在 Free-Model-Hub UI 中添加"导出 Hermes 配置"按钮 | 0.5 天 |
| **Phase 4** | 开发 Hermes 插件（自动同步） | 2-3 天 |

---

## 六、风险与注意事项

1. **API Key 安全**：生成的配置中包含 `.env` 变量引用（`${SLUG}_API_KEY`），而非明文，确保安全
2. **base_url 兼容性**：部分提供商（如 Gemini）不是 OpenAI 兼容端点，需要特殊处理
3. **配置膨胀**：如果导出所有模型，Hermes 配置会变得过大，建议只导出 Tier 1+2 的免费模型
4. **双向同步**：Free-Model-Hub 中隐藏的提供商不应出现在 Hermes 配置中