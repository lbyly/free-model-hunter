#!/usr/bin/env python3
"""
sync_fhm_to_hermes.py —— 从 FMH 插件缓存 + scrapers 读取 provider 数据，
将 FMH providers 写入 Hermes config.yaml 的 custom_providers: 部分。

这些 provider 之前在 FMH 插件中通过 register_profile() 注册到了
providers._REGISTRY，但 list_authenticated_providers() 从不读取 _REGISTRY，
因此 Desktop 的模型选择器看不到它们。

解决方案：将 FMH provider 信息写入 config.yaml 的 custom_providers: 列表，
这样 Section 4 的 list_authenticated_providers() 就能读取它们。
"""

import json, os, sys
from pathlib import Path
from copy import deepcopy

# ── 配置 ──────────────────────────────────────────────────────────────────
HERMES_HOME = Path(os.environ.get("HERMES_HOME", "C:/Users/Administrator/.hermes"))
FMH_CACHE = HERMES_HOME / "plugins" / "model-providers" / "free-model-hub" / ".fmh_providers_cache.json"
CONFIG_PATH = HERMES_HOME / "config.yaml"

# ── 已知 FMH scrapers 的 endpoint 配置 ──────────────────────────────────
# 这些信息来自 scrapers/*.py 中的 chat_endpoint_base / chat_api_key
SCRAPER_META = {
    "agnes": {
        "display_name": "Agnes AI",
        "base_url": "https://apihub.agnes-ai.com/v1",
        "key_env": "AGNES_API_KEY",
        "discover_models": False,
    },
    "cerebras": {
        "display_name": "Cerebras",
        "base_url": "https://api.cerebras.ai/v1",
        "key_env": "CEREBRAS_API_KEY",
        "discover_models": True,
    },
    "groq": {
        "display_name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "discover_models": True,
    },
    "mollinations": {
        "display_name": "Mollinations.ai",
        "base_url": "https://gen.pollinations.ai/v1",
        "key_env": "MOLLINATIONS_API_KEY",
        "discover_models": True,
    },
    "nvidia": {
        "display_name": "NVIDIA",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "key_env": "NVIDIA_API_KEY",
        "discover_models": True,
    },
    "xai": {
        "display_name": "X.ai",
        "base_url": "https://api.x.ai/v1",
        "key_env": "XAI_API_KEY",
        "discover_models": True,
    },
    "sensenova": {
        "display_name": "商汤日日新",
        "base_url": "https://api.sensenova.cn/v1",
        "key_env": "SENSENOVA_API_KEY",
        "discover_models": True,
    },
    "alibaba_bailian": {
        "display_name": "阿里云百炼",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "key_env": "ALIBABA_BAILIAN_API_KEY",
        "discover_models": True,
    },
}

print("=" * 60)
print("FMH → Hermes Config Sync")
print("=" * 60)

# ── 1. 读取 FMH 插件缓存 ─────────────────────────────────────────────────
print(f"\n[1/5] 读取 FMH 插件缓存: {FMH_CACHE}")
if not FMH_CACHE.exists():
    print(f"  ✗ 缓存文件不存在！")
    sys.exit(1)

with open(FMH_CACHE, "r", encoding="utf-8") as f:
    fmh_providers = json.load(f)

print(f"  ✓ 读取到 {len(fmh_providers)} 个 FMH providers")
for p in fmh_providers:
    n = p.get("name", "?")
    models = p.get("models", {})
    print(f"    - {n}: {len(models)} models")

# ── 2. 构建 custom_providers 条目 ────────────────────────────────────────
print(f"\n[2/5] 构建 custom_providers 条目...")

custom_entries = []
for pdata in fmh_providers:
    name = pdata.get("name", "").strip()
    if not name:
        continue

    # 从缓存中获取 base_url
    base_url = (pdata.get("base_url") or "").strip().rstrip("/")

    # 查找对应的 scraper meta 以获取 key_env
    key_env = ""
    for slug, meta in SCRAPER_META.items():
        if meta["display_name"] == name:
            key_env = meta["key_env"]
            if not base_url:
                base_url = meta["base_url"]
            break

    if not base_url:
        print(f"  ⚠ 跳过 {name}: 无 base_url")
        continue

    # 从缓存中获取 models 列表
    models_dict = pdata.get("models", {})
    model_ids = sorted(models_dict.keys()) if isinstance(models_dict, dict) else []

    # 构建 custom_providers 条目
    entry = {"name": name, "base_url": base_url}
    if key_env:
        entry["key_env"] = key_env
    else:
        entry["api_key"] = ""

    # 设置 discover_models 为 True，让 Hermes 自动发现模型
    entry["discover_models"] = False

    # 仍然显式列出模型（作为 fallback）
    if model_ids:
        entry["models"] = model_ids

    custom_entries.append(entry)
    print(f"  + {name}: {len(model_ids)} models, key_env={key_env}")

print(f"\n  共构建 {len(custom_entries)} 个 custom_providers 条目")

# ── 3. 读取现有 config.yaml ──────────────────────────────────────────────
print(f"\n[3/5] 读取 {CONFIG_PATH}")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    raw = f.read()

lines = raw.split("\n")

# ── 4. 写入 custom_providers ─────────────────────────────────────────────
print(f"\n[4/5] 写入 custom_providers...")

# 构建 YAML 块
yaml_lines = []
yaml_lines.append("custom_providers:")
for entry in custom_entries:
    yaml_lines.append(f'  - name: "{entry["name"]}"')
    yaml_lines.append(f'    base_url: "{entry["base_url"]}"')
    if "key_env" in entry:
        yaml_lines.append(f'    key_env: "{entry["key_env"]}"')
    else:
        yaml_lines.append(f'    api_key: ""')
    if "discover_models" in entry:
        yaml_lines.append(f'    discover_models: {str(entry["discover_models"]).lower()}')
    models = entry.get("models", [])
    if models:
        yaml_lines.append("    models:")
        for m in models:
            yaml_lines.append(f'      - "{m}"')

custom_yaml = "\n".join(yaml_lines)

# 检查是否已存在 custom_providers:
has_custom = any(line.strip().startswith("custom_providers:") for line in lines)

if has_custom:
    # 替换旧的 custom_providers 块
    print("  检测到已存在的 custom_providers，正在替换...")
    new_lines = []
    skip = False
    for line in lines:
        stripped = line.strip()
        if stripped == "custom_providers:":
            skip = True
            new_lines.append(line)
            new_lines.extend(yaml_lines[1:])
            continue
        if skip:
            if stripped == "" or line[0] in (" ", "\t"):
                continue
            else:
                skip = False
                new_lines.append(line)
        else:
            new_lines.append(line)
    raw = "\n".join(new_lines)
    print("  ✓ 已替换")
else:
    # 在 providers: {} 后插入
    print("  未找到 custom_providers，正在插入...")
    marker = "providers: {}"
    if marker in raw:
        raw = raw.replace(marker, marker + "\n" + custom_yaml, 1)
        print("  ✓ 已在 providers: {} 后插入")
    else:
        raw = raw.rstrip() + "\n" + custom_yaml
        print("  ✓ 已追加到文件末尾")

with open(CONFIG_PATH, "w", encoding="utf-8") as f:
    f.write(raw)

print(f"  ✓ {len(custom_entries)} 个 provider 已写入 config.yaml")

# ── 5. 删除 FMH 插件缓存（强制下次重新加载） ─────────────────────────────
print(f"\n[5/5] 清理 FMH 插件缓存...")
if FMH_CACHE.exists():
    FMH_CACHE.unlink()
    print(f"  ✓ 已删除: {FMH_CACHE}")
else:
    print(f"  - 缓存不存在，无需删除")

print("\n" + "=" * 60)
print("完成！请重启 Hermes Desktop 以加载新的 providers。")
print("=" * 60)
