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

## 三、方案探索历程

### 3.1 方案 A（尝试→放弃）：Hermes Model Catalog API

**实现**：创建了 [`backend/api/hermes_catalog.py`](/backend/api/hermes_catalog.py:1-158)，`GET /api/hermes/catalog` 返回 JSON manifest（15 providers, 146 models）。

**问题**：Hermes 的 `model_catalog` 模块（[`model_catalog.py`](C:/Users/Administrator/.hermes/hermes-agent/hermes_cli/model_catalog.py:324-356)）只消费 catalog 中名为 `"openrouter"` 和 `"nous"` 的 provider block，用于 `get_curated_openrouter_models()` 和 `get_curated_nous_models()`，**不用于通用模型选择器**。

**根本原因**：Hermes 的 `/switch-model` 使用 [`list_authenticated_providers()`](C:/Users/Administrator/.hermes/hermes-agent/hermes_cli/model_switch.py:1176-1958)，其数据来源为：
1. `_PROVIDER_MODELS`（硬编码字典，[`models.py:152-492`](C:/Users/Administrator/.hermes/hermes-agent/hermes_cli/models.py)）
2. `cached_provider_model_ids()`（实时 API 拉取）
3. `PROVIDER_TO_MODELS_DEV`（远程 models.dev 服务）
4. **`custom_providers`**（用户 config.yaml 配置）

→ **结论**: Catalog API 无法让自定义模型出现在 `/switch-model` 列表。

### 3.2 方案 C（评估→搁置）：Hermes 插件

Hermes 的插件机制（[`providers/__init__.py`](C:/Users/Administrator/.hermes/hermes-agent/providers/__init__.py:53-62)）支持 `register_provider()` 注册 `ProviderProfile`（运行时配置），但**不填充模型选择器列表**。插件仅控制运行时行为（transport, auth, api_mode），而 `/switch-model` 的列表来自上述 4 个来源。

**示例**：现有插件 [`opencode-zen`](C:/Users/Administrator/.hermes/hermes-agent/plugins/model-providers/opencode-zen/__init__.py:1-117) 注册了 `ProviderProfile`，但其模型仍需在 config.yaml 的 `custom_providers:` 中定义才能出现在 `/switch-model`。

### 3.3 ✅ 方案 A'（最终选择）：配置导出 API

**核心思路**：Free-Model-Hub 提供 API 端点，自动生成 Hermes `custom_providers` YAML 配置块，直接复制到 config.yaml。

---

## 四、最终实现

### 4.1 API 端点

**文件**: [`backend/api/hermes_config_export.py`](/backend/api/hermes_config_export.py:1-196)

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/hermes/providers-config` | GET | 生成 Hermes custom_providers YAML |
| `?format=json` | GET | 返回 JSON 格式（程序化使用） |

**参数**:
- `format`: `yaml`（默认）或 `json`
- `include_public`: 是否包含无 API key 的公共提供商（默认 `false`）
- `include_models`: 是否包含模型列表（默认 `true`）

### 4.2 数据流

```
Free-Model-Hub (localhost:8000)
  │
  │  GET /api/hermes/providers-config
  │
  ▼
  查询 SQLite:
  ├── providers (is_active=1, hidden=0)
  └── models (provider_id → model_id, context_window)
  │
  ▼
  交叉引用爬虫配置:
  └── scraper.chat_endpoint_base → base_url
  └── config.SLUG_TO_API_KEY_VAR  → api_key
  │
  ▼
  输出 YAML → 复制到 config.yaml → /switch-model 可见
```

### 4.3 数据来源

| 字段 | 来源 | 说明 |
|---|---|---|
| `name` | `providers.name` | 提供商显示名 |
| `base_url` | `scraper.chat_endpoint_base` | 从爬虫类读取 OpenAI 兼容端点 |
| `api_key` | [`config.get_api_key_for_slug()`](/backend/config.py:73-78) | 从 .env 或硬编码 dev key 读取 |
| `model` | 该提供商默认模型 | 第一个模型 ID |
| `models.{id}.context_length` | `models.context_window` | 上下文窗口大小 |

### 4.4 合并结果

**目标文件**: `~/.hermes/config.yaml:564-635` → 现有 `custom_providers:` 被追加 6 个新提供商

| 提供商 | 模型数 | 状态 |
|---|---|---|
| Cerebras | 2 | 新增 |
| Groq | 12 | 新增 |
| Mollinations.ai | 11 | 新增 |
| NVIDIA | 45 | 新增 |
| X.ai | 4 | 新增 |
| 阿里云百炼 | 6 | 新增 |
| Agnes AI | 2 | 已存在（合并跳过） |
| 商汤日日新 | 3 | 已存在（合并跳过） |

### 4.5 验证结果

在 Hermes 终端运行 `/switch-model` 后，所有新增提供商的模型均出现在候选列表中。

---

## 五、关键发现

1. **Hermes Model Catalog 不是通用模型注册表**：仅用于 "openrouter" 和 "nous" 两个 provider 的精选列表，不影响 `/switch-model` 选择器。
2. **模型选择器的数据源**：`custom_providers` 是唯一能让自定义模型出现在 `/switch-model` 中的机制。
3. **插件 ≠ 模型列表**：Hermes 的 `ProviderProfile` 插件只控制运行时调用行为（transport, auth, api_mode），不贡献模型选择器条目。
4. **base_url 是关键**：Free-Model-Hub 的爬虫配置中 `chat_endpoint_base`（如 `https://api.groq.com/openai/v1`）是生成 Hermes 配置的关键字段。

---

## 六、未来优化方向

1. **定期同步**：在 Free-Model-Hub 的 scheduler 中添加自动重新生成配置的功能
2. **UI 集成**：在 Web UI 中添加"一键同步到 Hermes"按钮，直接修改 `~/.hermes/config.yaml`
3. **增量更新**：比较两次 scrape 结果，只推送新增/删除的模型
4. **Tier 过滤**：允许用户选择只导出特定 Tier 的模型，避免配置膨胀
5. **api_key 模板化**：在 YAML 中使用 `${SLUG}_API_KEY` 变量引用而非明文 key