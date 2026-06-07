"""
Free Models Hub 配置
支持通过环境变量或 .env 文件配置
"""
import os
from pathlib import Path

# 尝试加载 .env 文件（可选）
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent

# 数据库
DATABASE_PATH = os.getenv("DATABASE_URL", str(BASE_DIR.parent / "data" / "models.db"))

# 爬虫定时（北京时间 24h 格式）
SCHEDULE_HOURS = os.getenv("SCHEDULE_HOURS", "2,14")

# 爬虫 HTTP 请求超时（秒）
SCRAPER_TIMEOUT = int(os.getenv("SCRAPER_TIMEOUT", "30"))

# Playwright 无头浏览器设置
PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"

# ===== API Keys（可选，用于需要认证的 Provider API） =====
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
COHERE_API_KEY = os.getenv("COHERE_API_KEY", "")
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
ALIBABA_API_KEY = os.getenv("ALIBABA_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
XAI_API_KEY = os.getenv("XAI_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
ANYROUTER_API_KEY = os.getenv("ANYROUTER_API_KEY", "")
NOTDIAMOND_API_KEY = os.getenv("NOTDIAMOND_API_KEY", "")
AGNES_API_KEY = os.getenv("AGNES_API_KEY", "")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")
OPENCODE_API_KEY = os.getenv("OPENCODE_API_KEY", "")
MOLLINATIONS_API_KEY = os.getenv("MOLLINATIONS_API_KEY", "")
SENSENOVA_API_KEY = os.getenv("SENSENOVA_API_KEY", "")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")


# ===== Provider slug → API Key 环境变量映射 =====
# 通过 provider slug 查表获取对应的 API Key
SLUG_TO_API_KEY_VAR = {
    "groq": "GROQ_API_KEY",
    "cohere": "COHERE_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "alibaba_bailian": "ALIBABA_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "xai": "XAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "anyrouter": "ANYROUTER_API_KEY",
    "notdiamond": "NOTDIAMOND_API_KEY",
    "agnes": "AGNES_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
    "opencode": "OPENCODE_API_KEY",
    "mollinations": "MOLLINATIONS_API_KEY",
    "sensenova": "SENSENOVA_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
}


def get_api_key_for_slug(slug: str) -> str:
    """根据 provider slug 获取对应的 API Key。未配置则返回空串。"""
    if not slug:
        return ""
    var_name = SLUG_TO_API_KEY_VAR.get(slug) or f"{slug.upper()}_API_KEY"
    return os.getenv(var_name, "")


def update_api_key_for_slug(slug: str, api_key: str):
    """更新/保存 provider 的 API key 到环境变量和 .env 文件中"""
    if not slug:
        return
    var_name = SLUG_TO_API_KEY_VAR.get(slug) or f"{slug.upper()}_API_KEY"
    
    # 1. 更新当前运行期的环境变量
    import os
    os.environ[var_name] = api_key
    
    # 2. 更新 .env 文件
    from pathlib import Path
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        try:
            env_path.touch()
        except Exception:
            pass
            
    lines = []
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            pass
            
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{var_name}="):
            lines[i] = f"{var_name}={api_key}\n"
            found = True
            break
            
    if not found:
        if lines and not lines[-1].endswith("\n"):
            lines.append("\n")
        lines.append(f"{var_name}={api_key}\n")
        
    try:
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception as e:
        print(f"Error saving to .env file: {e}")

    # 3. 动态更新内存中所有相关模块引用的变量及 Scraper 类的 chat_api_key 属性
    import sys
    # 先更新 config 模块的全局变量自身
    import config
    setattr(config, var_name, api_key)
    
    for mod_name, module in list(sys.modules.items()):
        if module and (mod_name == "config" or mod_name.startswith("scrapers.")):
            # 更新模块中的全局变量
            if hasattr(module, var_name):
                try:
                    setattr(module, var_name, api_key)
                except Exception:
                    pass
            # 更新 Scraper 类本身的属性
            for attr_name in dir(module):
                try:
                    attr = getattr(module, attr_name, None)
                    if isinstance(attr, type):
                        # 判断是否为 Scraper 类，避免在 base 模块中执行
                        if attr_name != "BaseScraper" and hasattr(attr, "provider_slug") and hasattr(attr, "chat_api_key"):
                            if getattr(attr, "provider_slug") == slug:
                                setattr(attr, "chat_api_key", api_key)
                except Exception:
                    pass
