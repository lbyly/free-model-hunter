#!/usr/bin/env python3
"""
sync_fhm_to_hermes2.py — 使用 yaml 安全地写入 FMH providers 到 config.yaml。
避免之前字符串替换导致的 YAML 损坏问题。
"""
import json, os, sys, shutil
from pathlib import Path
from copy import deepcopy

# 使用 Hermes venv 的 Python 和 pyyaml
import yaml

# ── 配置 ──────────────────────────────────────────────────────────────────
HERMES_HOME = Path("C:/Users/Administrator/AppData/Local/hermes")
FMH_CACHE = Path("d:/Free-Model-Hub/_fmh_providers.json")
CONFIG_PATH = HERMES_HOME / "config.yaml"

# 已知的 scraper 元数据 (slug -> key_env)
SCRAPER_META = {
    "ag": ("AGNES_API_KEY", "Agnes AI"),
    "ce": ("CEREBRAS_API_KEY", "Cerebras"),
    "gr": ("GROQ_API_KEY", "Groq"),
    "mo": ("MOLLINATIONS_API_KEY", "Mollinations.ai"),
    "nv": ("NVIDIA_API_KEY", "NVIDIA"),
    "xa": ("XAI_API_KEY", "X.ai"),
    "se": ("SENSENOVA_API_KEY", "商汤日日新"),
    "al": ("ALIBABA_BAILIAN_API_KEY", "阿里云百炼"),
}

def _find_key_env(name: str) -> str:
    for env, display_name in SCRAPER_META.values():
        if name.lower() == display_name.lower() or name.lower() in display_name.lower():
            return env
    # Fuzzy match
    name_lower = name.lower()
    if "agnes" in name_lower:
        return "AGNES_API_KEY"
    if "cerebras" in name_lower:
        return "CEREBRAS_API_KEY"
    if "groq" in name_lower:
        return "GROQ_API_KEY"
    if "mollin" in name_lower or "pollin" in name_lower:
        return "MOLLINATIONS_API_KEY"
    if "nvidia" in name_lower:
        return "NVIDIA_API_KEY"
    if "x.ai" in name_lower or "xai" in name_lower:
        return "XAI_API_KEY"
    if "sensenova" in name_lower or "商汤" in name_lower:
        return "SENSENOVA_API_KEY"
    if "alibaba" in name_lower or "bailian" in name_lower or "阿里云" in name_lower or "百炼" in name_lower:
        return "ALIBABA_BAILIAN_API_KEY"
    return ""

print("=" * 60)
print("FMH → Hermes Config Sync v2 (yaml-based)")
print("=" * 60)

# ── 1. 读取 FMH 插件缓存 ─────────────────────────────────────────────────
print(f"\n[1/4] 读取 FMH 插件缓存: {FMH_CACHE}")
if not FMH_CACHE.exists():
    print(f"  [!] 缓存文件不存在！")
    sys.exit(1)

with open(FMH_CACHE, "r", encoding="utf-8") as f:
    fmh_providers = json.load(f)

print(f"  [+] 读取到 {len(fmh_providers)} 个 FMH providers")

# ── 2. 读取当前配置 ─────────────────────────────────────────────────────
print(f"\n[2/4] 读取当前配置: {CONFIG_PATH}")

# 先备份
backup = CONFIG_PATH.with_suffix(".yaml.bak2")
shutil.copy2(CONFIG_PATH, backup)
print(f"  [+] 已备份到 {backup}")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

if config is None:
    config = {}

print(f"  当前配置包含 keys: {list(config.keys())[:15]}")

# ── 3. 构建 custom_providers ──────────────────────────────────────────
print(f"\n[3/4] 构建 custom_providers...")

# 删除旧的自定义 providers 中属于 FMH 的部分（通过 slug/name 匹配）
# 但保留用户自定义的 providers (Omnirouter, Cpamc, Blazeai, Ds2api)
old_custom = config.get("custom_providers", [])
if old_custom is None:
    old_custom = []

# 构建新的 FMH 条目
new_custom = []
for pdata in fmh_providers:
    name = pdata.get("name", "").strip()
    base_url = (pdata.get("base_url") or "").strip().rstrip("/")
    if not name or not base_url:
        continue
    
    key_env = _find_key_env(name)
    models_dict = pdata.get("models", {})
    model_ids = sorted(models_dict.keys()) if isinstance(models_dict, dict) else []
    
    entry = {
        "name": name,
        "base_url": base_url,
        "key_env": key_env,
        "discover_models": False,
    }
    if model_ids:
        entry["models"] = model_ids
    
    new_custom.append(entry)
    print(f"  [+] {name}: {len(model_ids)} models, key_env={key_env}")

# 保留非 FMH 的自定义 providers（如果有）
fmh_names_lower = {p.get("name", "").strip().lower() for p in fmh_providers}
preserved = []
for cp in old_custom:
    if not isinstance(cp, dict):
        preserved.append(cp)
        continue
    cp_name = str(cp.get("name", "")).strip().lower()
    # 跳过 FMH providers（将被替换）
    if cp_name in fmh_names_lower:
        continue
    # 也跳过 key_env 指向 FMH 的
    cp_key_env = str(cp.get("key_env", "")).strip().upper()
    fmh_key_envs = {_find_key_env(n) for n in [p.get("name","") for p in fmh_providers]}
    if cp_key_env in fmh_key_envs and cp_key_env:
        continue
    preserved.append(cp)

if preserved:
    print(f"  [+] 保留 {len(preserved)} 个已有的非 FMH custom_providers 条目")
    # FMH 条目放在前面，非 FMH 条目放在后面
    all_custom = new_custom + preserved
else:
    print(f"  [!] 没有已有的非 FMH custom_providers 条目")
    all_custom = new_custom

# ── 4. 写回配置 ─────────────────────────────────────────────────────────
print(f"\n[4/4] 写回配置...")
config["custom_providers"] = all_custom

with open(CONFIG_PATH, "w", encoding="utf-8") as f:
    yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False, indent=2)

print(f"  [+] 已写入 {len(all_custom)} 个 custom_providers 条目到 {CONFIG_PATH}")

# 验证写入的 YAML 可以被正确解析
print(f"\n  验证中...")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    validated = yaml.safe_load(f)
validated_custom = validated.get("custom_providers", [])
print(f"  [+] 验证通过: {len(validated_custom)} 个 custom_providers 条目")

# ── 5. 删除 FMH 插件缓存 ─────────────────────────────────────────────
if FMH_CACHE.exists():
    FMH_CACHE.unlink()
    print(f"  [+] 已删除 FMH 插件缓存: {FMH_CACHE}")

print("\n" + "=" * 60)
print("完成！请重启 Hermes Desktop 以加载新的 providers。")
print("=" * 60)
