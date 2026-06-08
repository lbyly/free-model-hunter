# Free-Model-Hub × Hermes 插件集成方案

> **⚠️ 本方案已被替代**
>
> 经过深入分析发现，Hermes 的 `ProviderProfile` 插件机制仅控制运行时调用行为（transport、auth、api_mode），**不填充模型选择器列表**。模型列表的来源是 `custom_providers`（config.yaml 配置节）。
>
> **最终方案已变更为 `方案 A'`**：Free-Model-Hub 新增 `GET /api/hermes/providers-config` API 端点，自动生成 Hermes `custom_providers` YAML 配置块。
>
> 详情见 [hermes-integration-analysis.md](./hermes-integration-analysis.md#33--最终选择配置导出-api)

> 更新日期: 2026-06-07
> 分支: `research/hermes-integration`

## 前置研究：Hermes 插件机制

### 插件类型

Hermes 有两种可插拔接口与模型相关：

| 接口 | 文件位置 | 说明 |
|---|---|---|
| **Model Provider 插件** | `~/.hermes/hermes-agent/plugins/model-providers/<name>/` | 注册新推理后端（如 NVIDIA、OpenRouter、Gemini） |
| **用户 Model Provider 插件** | `~/.hermes/plugins/model-providers/<name>/` | 用户自定义，覆盖内置插件 |
| **Custom Provider 配置** | `~/.hermes/config.yaml → custom_providers` | 配置驱动，声明 OpenAI 兼容端点 |

### Model Provider 插件结构

每个插件目录包含：
1. **`plugin.yaml`** — 清单文件
2. **`__init__.py`** — 调用 `register_provider(profile)` 注册 Provider

示例（内置 `custom` 插件）：

```python
# plugin.yaml
name: custom-provider
kind: model-provider
version: 1.0.0
description: Custom / Ollama / local OpenAI-compatible endpoint

# __init__.py
from providers import register_provider
from providers.base import ProviderProfile

custom = ProviderProfile(
    name="custom",
    base_url="",           # 由用户配置
    env_vars=(),           # 没有固定 API Key
)
register_provider(custom)
```

### 当前 Free-Model-Hub 的使用方式

你的 `~/.hermes/config.yaml` 中已经通过 `custom_providers` 配置了多个自定义提供商（Omnirouter、Ds2api、Cpamc、Blazeai 等），但它们是**手动管理**的。

---

## 推荐的插件方案

**推荐方案**: **Model Catalog API + 配置参考**（零代码，零插件）

Hermes 原生支持 `model_catalog` 功能，可以远程拉取模型目录。Free-Model-Hub 只需新增一个 API 端点，Hermes 端无需任何插件即可使用。

### 架构图

```
┌─────────────────────┐         ┌──────────────────────┐
│  Free-Model-Hub     │         │  Hermes              │
│                     │         │                      │
│  SQLite DB ──► REST │ ◄────── │  model_catalog.url   │
│  (20+ providers)    │  JSON   │  └─→ 自动解析模型列表   │
│                     │         │                      │
│  GET /api/hermes/   │         │  custom_providers    │
│  catalog            │         │  └─→ 引用上述模型      │
└─────────────────────┘         └──────────────────────┘
```

### 操作步骤

#### Step 1：Free-Model-Hub 新增 `/api/hermes/catalog` 端点

在 `d:/Free-Model-Hub/backend/api/` 下新增 `hermes.py` 路由文件：

```python
"""Hermes Model Catalog API — 输出 Hermes 兼容的模型目录"""
from fastapi import APIRouter
from models.repository import get_all_providers

router = APIRouter(prefix="/api/hermes", tags=["hermes"])

@router.get("/catalog")
async def hermes_catalog():
    """生成 Hermes model_catalog 格式的模型列表"""
    # 从数据库读取所有活跃提供商及其模型
    # 输出格式兼容 Hermes 的 model_catalog 协议
```

然后在 [`backend/main.py`](backend/main.py) 注册这个路由。

#### Step 2：配置 Hermes 的 `model_catalog`

在 `~/.hermes/config.yaml` 中添加：

```yaml
model_catalog:
  enabled: true
  url: http://localhost:8000/api/hermes/catalog  # Free-Model-Hub 地址
  ttl_hours: 1                                    # 每小时刷新一次
```

#### Step 3：重启 Hermes

```bash
hermes doctor   # 检查配置
hermes          # 重新启动
```

### 无需开发插件的理由

1. **Hermes 已有 `model_catalog` 机制** — 原生支持远程模型目录
2. **无需改 Hermes 代码** — 纯配置驱动
3. **Free-Model-Hub 只需新增一个端点** — 改动最小
4. **实时同步** — Free-Model-Hub 爬取到新模型后，Hermes 自动感知

---

## 方案二：Free-Model-Hub Model Provider 插件

如果 `model_catalog` 不能满足需求（例如需要自定义 API Key 映射逻辑），可以开发一个真正的 Model Provider 插件。

### 插件位置

```
~/.hermes/plugins/model-providers/free-model-hub/
├── plugin.yaml
└── __init__.py
```

### plugin.yaml

```yaml
name: free-model-hub
kind: model-provider
version: 1.0.0
description: Free Model Hub — aggregated free AI models from 20+ providers
author: Free-Model-Hub
requires_env:
  - FREE_MODEL_HUB_URL   # Free-Model-Hub 后端地址
```

### __init__.py

```python
"""Free-Model-Hub provider — 自动发现并使用免费模型"""
import httpx
from providers import register_provider
from providers.base import ProviderProfile


class FreeModelHubProfile(ProviderProfile):
    """从 Free-Model-Hub 动态获取模型列表"""
    
    def fetch_models(self, *, api_key=None, timeout=8.0):
        """向 Free-Model-Hub API 请求可用模型列表"""
        hub_url = os.environ.get("FREE_MODEL_HUB_URL", "http://localhost:8000")
        try:
            resp = httpx.get(f"{hub_url}/api/models", 
                           params={"page_size": 200},
                           timeout=timeout)
            data = resp.json()
            # 解析为 model_id 列表
            return [m["model_id"] for m in data.get("models", [])]
        except Exception:
            return None


profile = FreeModelHubProfile(
    name="free-model-hub",
    base_url="",  # 在 config.yaml 的 custom_providers 中配置实际端点
    env_vars=("FREE_MODEL_HUB_URL",),
)
register_provider(profile)
```

### 然后在 `config.yaml` 中使用

```yaml
custom_providers:
  - name: FreeModelHub
    base_url: http://localhost:8000/api
    provider: free-model-hub    # 引用上面注册的 provider 插件
    model: "*"                  # 通配所有模型
```

---

## 推荐结论

| 方案 | 开发量 | 维护成本 | 灵活性 | 推荐 |
|---|---|---|---|---|
| **Model Catalog API** | 低（1 个 API 端点） | 低 | 中 | ⭐ **首选** |
| **Model Provider 插件** | 中（一个 Python 包） | 低 | 高 | 备选 |
| **导出脚本** | 低 | 高 | 低 | ❌ 已排除 |

**先试 Model Catalog API**——这是改动最小、Hermes 原生支持的方案。如果后期需要更复杂的逻辑（如按 tier 筛选、API Key 自动填充等），再升级为完整的 Model Provider 插件。