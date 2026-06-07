"""
模型分类引擎

按能力分三级 (Tier 1/2/3) + 按用途分类 (chat/image/reasoning/code/embedding/vision/audio/reranker)
"""
import re
from typing import Optional

# ============================================================
# 能力分级 (Tier)
# ------------------------------------------------------------
# Tier 1 - 旗舰级：顶级大参数模型、SOTA 能力
# Tier 2 - 增强级：中参数、高效模型，足以处理大多数任务
# Tier 3 - 基础级：小参数、专用模型（嵌入、重排、轻量对话）
# ============================================================

# Tier 1 关键词：优先匹配
_TIER1_KEYWORDS = [
    r"\bgpt-5[\.\d]*(?:-pro)?\b",          # GPT-5, GPT-5.1, GPT-5.4-pro
    r"\bgpt-5-pro\b",
    r"\bgpt-5\.\d+-pro\b",
    r"\bgpt-oss-120b\b",
    r"\bclaude-4\b",
    r"\bclaude-3\.5\b",
    r"\bclaude-opus\b",
    r"\bgemini-2\.0-pro\b",
    r"\bgemini-2\.5\b",
    r"\bgemini-2\.0-flash-thinking\b",
    r"\bdeep-research-max\b",
    r"\bDeepSeek-R1\b",                     # 671B MoE
    r"\bDeepSeek-V[34]\b",                  # DeepSeek-V3/V4
    r"\bDeepSeek-V[34]\.\d+\b",
    r"\bDeepSeek-V4-Pro\b",
    r"\bgrok-4(?:\.\d+)?\b",                # Grok 4.x
    r"\bgrok-4\.20\b",
    r"\bgrok-build\b",
    r"\bcommand-a-(?:plus|reasoning)\b",
    r"\bcommand-r-plus\b",
    r"\bqwen2\.5-72b\b",                    # 72B 旗舰
    r"\bqwen3(?:\.\d+)?-max\b",             # Qwen3.x Max
    r"\bqwen3-32b\b",                       # Qwen3 32B
    r"\bqwen3\.7-max\b",
    r"\bqwen3\.6-max-preview\b",
    r"\bkimi-k2(?:\.\d+)?\b",               # Kimi K2.x
    r"\bkimi-latest\b",
    r"\bgpt-latest\b",
    r"\bgpt-chat-latest\b",
    r"\bgpt-mini-latest\b",
    r"\bglm-[45](?:\.\d+)?\b",              # GLM-4, GLM-5, GLM-5.1
    r"\bhunyuan-a13b\b",
    r"\bling-2\.6-1t\b",
    r"\bring-2\.6-1t\b",
    r"\bllama-3\.3-70b\b",
    r"\bllama-3\.1-405b\b",
    r"\bhermes-4-405b\b",
    r"\bhermes-4-70b\b",
    r"\bhermes-3-llama-3\.1-405b\b",
    r"\bhermes-3-llama-3\.1-70b\b",
    r"\bintellect-3\b",
    r"\bsonar-reasoning-pro\b",
    r"\bsonar-deep-research\b",
    r"\binflection-3-pi\b",
    r"\bstep-3(?:\.\d+)?-(?:flash|max)\b",  # 阶跃星辰
    r"\bseed-(?:1\.6|2\.0)\b",
    r"\bhy3-preview\b",
    r"\bqwen3\.7-plus\b",
    r"\bqwen3\.6-plus\b",
    r"\bminimax-m2\.5\b",
    r"\bnex-n2-pro\b",
    r"\bgpt-5\.4-image-2\b",
]

# Tier 2 关键词
_TIER2_KEYWORDS = [
    r"\bgpt-4o(?!-mini)\b",
    r"\bgpt-4\.1(?!-nano)\b",
    r"\bgpt-4\.1-mini\b",
    r"\bgpt-4-turbo\b",
    r"\bgpt-4\b(?!-mini)",
    r"\bo[123]-mini\b",
    r"\bo1\b(?!-mini)",
    r"\bgemini-2\.0-flash(?!-thinking)\b",
    r"\bgemini-1\.5-pro\b",
    r"\bgemini-1\.5-flash\b",
    r"\bgemini-2\.0-flash-image-gen\b",
    r"\bgemini-2\.0-pro-exp\b",
    r"\bgemini-2\.0-flash-lite\b",
    r"\bclaude-3-haiku\b",
    r"\bclaude-3-sonnet\b",
    r"\bgrok-3\b",
    r"\bgrok-3\.\d+\b",
    r"\bcommand-r(?!-plus|-7b)\b",
    r"\bcommand-a(?:-|\b)(?!-plus|-reasoning)\b",
    r"\bcommand-a-vision-07-2025\b",
    r"\bcohere-transcribe\b",
    r"\bc4ai-aya-expanse-32b\b",
    r"\bc4ai-aya-vision-32b\b",
    r"\bDeepSeek-V3\.2\b",
    r"\bDeepSeek-V4-Flash\b",
    r"\bDeepSeek-OCR\b",
    r"\bDeepSeek-R1-0528-Qwen3-8B\b",
    r"\bqwen2\.5-(?:32b|14b)\b",
    r"\bqwen3-14b\b",
    r"\bqwen3-30b-a3b\b",
    r"\bqwen3-8b\b",
    r"\bqwen3-vl-(?:32b|30b|8b)\b",
    r"\bqwen3-coder-30b\b",
    r"\bqwen3-omni-30b\b",
    r"\bllama-3\.1-70b\b",
    r"\bllama-3\.1-8b\b",
    r"\bllama-3\.3-70b\b",
    r"\bllama-4\b",
    r"\bmistral-large\b",
    r"\bmistral-small\b",
    r"\bpixtral\b",
    r"\bmixtral-8x7b\b",
    r"\bmixtral-8x22b\b",
    r"\bgemma-3\b",
    r"\bgemma-2-27b\b",
    r"\bgemma-2-9b\b",
    r"\bgpt-oss-20b\b",
    r"\bgpt-oss-safeguard-20b\b",
    r"\bgranite-4\b",
    r"\bhermes-3-llama-3\.1-70b\b",
    r"\bkat-coder-pro-v2\b",
    r"\bkimi-k2-thinking\b",
    r"\blfm-2-24b-a2b\b",
    r"\bl3-lunaris-8b\b",
    r"\bl3\.1-(?:70b|euryale)\b",
    r"\bl3\.3-euryale-70b\b",
    r"\bminimax-(?:abab-|mini\s*max\s*max)\b",
    r"\bqwen3-reranker-\d+b\b",
    r"\bqwen3-embedding-\d+b\b",
    r"\breka-flash-3\b",
    r"\breka-edge\b",
    r"\brocinante-12b\b",
    r"\bsolar-pro-3\b",
    r"\bsonar-pro\b",
    r"\bsonar\b",
    r"\bskyfall-36b-v2\b",
    r"\btrinity-large-thinking\b",
    r"\bunslopnemo-12b\b",
    r"\bui-tars-1\.5-7b\b",
    r"\bvoxtral-small-24b\b",
    r"\bwizardlm-2-8x22b\b",
    r"\bseed-(?:1\.6-flash|2\.0-lite|2\.0-mini)\b",
    r"\bgpt-5-mini\b",
    r"\bgpt-5-nano\b",
    r"\bgpt-5-chat\b",
    r"\bgpt-5-codex(?!-max|-mini)\b",
    r"\bgpt-5-image(?:-mini)?\b",
    r"\bgpt-5\.1(?:-chat|-codex(?!-max|-mini))?\b",
    r"\bgpt-5\.1-codex-mini\b",
    r"\bgpt-5\.2(?:-chat|-pro)?\b",
    r"\bgpt-5\.2-codex\b",
    r"\bgpt-5\.3(?:-chat)?\b",
    r"\bgpt-5\.3-codex\b",
    r"\bgpt-5\.4(?!-image-2)\b",
    r"\bgpt-5\.4-(?:mini|nano|pro)\b",
    r"\bgpt-5\.5(?:-pro)?\b",
    r"\bgpt-audio(?:-mini)?\b",
    r"\bgpt-4\.1-nano\b",
    r"\bgpt-4o-mini\b",
    r"\bclaude-3-5-haiku\b",
    r"\bgrok-4\.20-multi-agent\b",
]

# Tier 1 用排除（检查是否匹配到 Tier1 但实际上是 embedding 等）
_TIER1_EXCLUDE_TYPES = {"embedding", "reranker"}


def classify_capability_tier(
    name: str,
    model_id: str,
    model_type: str,
    provider: str,
    context_window: Optional[str] = None,
    description: str = "",
) -> int:
    """
    返回 1, 2, 3 分别对应 T1/T2/T3。
    规则：
      1. 先查 Tier 1 关键词
      2. 再查 Tier 2 关键词
      3. 其余归 Tier 3
    """
    text = f"{name} {model_id}".lower()
    provider_lower = provider.lower()

    # Embedding / Reranker 自动降 Tier 3
    if model_type in _TIER1_EXCLUDE_TYPES:
        return 3

    # 检查名称中含 embedding/reranker
    if re.search(r"\bembed\b", text) or re.search(r"\breranker\b", text):
        return 3

    # 小参数模型判断 (< 3B 自动降 T3)
    small_param = re.findall(r"(\d+)b", text.lower())
    if small_param:
        min_b = min(int(b) for b in small_param)
        if min_b <= 3:
            return 3
        # 7B-14B 除非明确 Tier 1 关键词，否则降 T2
        if min_b <= 9 and not any(re.search(k, text, re.IGNORECASE) for k in _TIER1_KEYWORDS):
            return 2

    # Tier 1 匹配
    if any(re.search(k, text, re.IGNORECASE) for k in _TIER1_KEYWORDS):
        return 1

    # Tier 2 匹配
    if any(re.search(k, text, re.IGNORECASE) for k in _TIER2_KEYWORDS):
        return 2

    # 剩余：检查是否为 embedding/reranker 类型
    if model_type in ("embedding", "reranker"):
        return 3

    # 如果名称包含 small/light/tiny/nano 等 → T3
    if re.search(r"\b(small|light|tiny|nano|mini)\b", text, re.IGNORECASE):
        # 但有些 mini 是 T2 级别的，如 GPT-4o-mini
        if re.search(r"\bgpt-4o-mini\b", text):
            return 2
        if re.search(r"\bgpt-4\.1-mini\b", text):
            return 2
        if re.search(r"\bgpt-5-mini\b", text):
            return 2
        if re.search(r"\bgpt-5-nano\b", text):
            return 2
        return 3

    # 明确是嵌入模型
    if re.search(r"\b(text-)?embed", text, re.IGNORECASE):
        return 3

    # 默认为 Tier 2
    return 2


# ============================================================
# 用途分类 (Use Case)
# ------------------------------------------------------------
# chat         通用对话
# image        图像生成
# reasoning    推理/思维链
# code         代码生成
# embedding    文本嵌入
# vision       视觉/多模态
# audio        音频/语音
# reranker     重排序
# ============================================================

_USE_CASE_RULES = [
    ("audio", re.compile(r"\b(audio|voice|speech|transcribe)\b", re.IGNORECASE)),
    ("embedding", re.compile(r"\b(embed|text-embedding)\b", re.IGNORECASE)),
    ("reranker", re.compile(r"\b(reranker|rerank)\b", re.IGNORECASE)),
    ("image", re.compile(r"\b(image|img|stable-diffusion|dall-e|kolors|sdxl|flux)\b", re.IGNORECASE)),
    ("vision", re.compile(r"\b(vl[-\s]|vision|visual|multimodal|omni|captioner|caption)\b", re.IGNORECASE)),
    ("reasoning", re.compile(r"\b(reasoner|reasoning|thinking|deep[\s-]?research)\b", re.IGNORECASE)),
    ("code", re.compile(r"\b(coder|codex|code[\s-]|gen[\s-]?code)\b", re.IGNORECASE)),
]

# 特定模型名称强制映射
_SPECIFIC_USE_CASE = {
    "deepseek-reasoner": "reasoning",
    "DeepSeek-R1": "reasoning",
    "DeepSeek-R1-0528-Qwen3-8B": "reasoning",
    "command-a-reasoning-08-2025": "reasoning",
    "command-a-vision-07-2025": "vision",
    "c4ai-aya-vision-32b": "vision",
    "gemini-2-0-flash-image-gen": "image",
    "gpt-5-image": "image",
    "gpt-5-image-mini": "image",
    "gpt-5.4-image-2": "image",
    "gpt-audio": "audio",
    "gpt-audio-mini": "audio",
    "cohere-transcribe-03-2026": "audio",
    "qwen-Image": "image",
    "qwen-Image-Edit": "image",
    "qwen-Image-Edit-2509": "image",
    "ERNIE-Image-Turbo": "image",
    "Kolors": "image",
}


def classify_use_case(
    name: str,
    model_id: str,
    model_type: str,
    provider: str,
    description: str = "",
) -> str:
    """
    返回 use_case: chat / image / reasoning / code / embedding / vision / audio / reranker
    """
    # 1. 先查 model_type 映射
    type_to_use_case = {
        "image": "image",
        "embedding": "embedding",
        "audio": "audio",
        "video": "vision",
    }
    if model_type in type_to_use_case:
        return type_to_use_case[model_type]

    # 2. 特定模型名称强制映射
    mid = model_id.strip()
    if mid in _SPECIFIC_USE_CASE:
        return _SPECIFIC_USE_CASE[mid]

    # 3. 名称规则匹配
    text = f"{name} {model_id} {description}"
    for uc, pattern in _USE_CASE_RULES:
        if pattern.search(text):
            return uc

    # 4. provider 级特殊规则
    provider_lower = provider.lower()
    if "embed" in provider_lower:
        return "embedding"

    # 5. model_type 为 code 的走 code
    if model_type == "code":
        return "code"

    # 6. 默认
    return "chat"


def classify_model(
    name: str,
    model_id: str,
    model_type: str,
    provider: str,
    context_window: Optional[str] = None,
    description: str = "",
) -> dict:
    """
    对单个模型进行完整分类。
    返回: {"capability_tier": 1|2|3, "use_case": "chat|..."}
    """
    tier = classify_capability_tier(name, model_id, model_type, provider, context_window, description)
    use_case = classify_use_case(name, model_id, model_type, provider, description)
    return {"capability_tier": tier, "use_case": use_case}