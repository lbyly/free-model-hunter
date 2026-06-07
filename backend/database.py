"""
SQLite 数据库连接与初始化
"""
import sqlite3
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from config import DATABASE_PATH


def get_connection() -> sqlite3.Connection:
    """获取数据库连接"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """上下文管理器方式获取数据库连接"""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate_schema():
    """迁移旧数据库 schema，添加新字段（兼容旧表）"""
    conn = get_connection()
    cursor = conn.cursor()

    # providers 表迁移
    cursor.execute("PRAGMA table_info(providers)")
    p_columns = [row[1] for row in cursor.fetchall()]

    if "hidden" not in p_columns:
        cursor.execute("ALTER TABLE providers ADD COLUMN hidden BOOLEAN DEFAULT 0")
        print("  [迁移] 添加 providers.hidden 列")

    # models 表迁移
    cursor.execute("PRAGMA table_info(models)")
    m_columns = [row[1] for row in cursor.fetchall()]

    if "capability_tier" not in m_columns:
        cursor.execute("ALTER TABLE models ADD COLUMN capability_tier INTEGER DEFAULT NULL")
        print("  [迁移] 添加 capability_tier 列")

    if "use_case" not in m_columns:
        cursor.execute("ALTER TABLE models ADD COLUMN use_case VARCHAR(30) DEFAULT 'chat'")
        print("  [迁移] 添加 use_case 列")

    # 新索引需要在列存在后才能创建
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_models_capability_tier ON models(capability_tier)")
    except Exception as e:
        print(f"  [迁移跳过索引] capability_tier: {e}")
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_models_use_case ON models(use_case)")
    except Exception as e:
        print(f"  [迁移跳过索引] use_case: {e}")

    conn.commit()
    conn.close()


def init_db():
    """初始化数据库，创建所有表"""
    # 先迁移旧表添加新字段
    migrate_schema()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS providers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL UNIQUE,
            slug VARCHAR(50) NOT NULL UNIQUE,
            website VARCHAR(255),
            scrape_url VARCHAR(255),
            scraper_class VARCHAR(100),
            is_active BOOLEAN DEFAULT 1,
            logo_url VARCHAR(255),
            last_scraped DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_id INTEGER NOT NULL,
            model_id VARCHAR(100) NOT NULL,
            name VARCHAR(200),
            description TEXT,
            type VARCHAR(50) DEFAULT 'chat',
            capability_tier INTEGER DEFAULT NULL,
            use_case VARCHAR(30) DEFAULT 'chat',
            is_free BOOLEAN DEFAULT 0,
            free_quota VARCHAR(255),
            pricing_url VARCHAR(255),
            context_window VARCHAR(50),
            tags TEXT DEFAULT '[]',
            status VARCHAR(20) DEFAULT 'active',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (provider_id) REFERENCES providers(id),
            UNIQUE(provider_id, model_id)
        );

        CREATE TABLE IF NOT EXISTS model_rate_limits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id INTEGER NOT NULL,
            rate_type VARCHAR(20) NOT NULL,
            limit_value INTEGER NOT NULL,
            tier VARCHAR(20) DEFAULT 'free',
            FOREIGN KEY (model_id) REFERENCES models(id)
        );

        CREATE TABLE IF NOT EXISTS scrape_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_id INTEGER NOT NULL,
            status VARCHAR(20) NOT NULL,
            model_count INTEGER DEFAULT 0,
            error_message TEXT,
            duration_seconds REAL,
            scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (provider_id) REFERENCES providers(id)
        );

        -- 索引
        CREATE INDEX IF NOT EXISTS idx_models_provider_id ON models(provider_id);
        CREATE INDEX IF NOT EXISTS idx_models_is_free ON models(is_free);
        CREATE INDEX IF NOT EXISTS idx_models_type ON models(type);
        CREATE INDEX IF NOT EXISTS idx_scrape_logs_provider_id ON scrape_logs(provider_id);
    """)

    # 单独创建新列索引（可能在迁移时已创建，这里 safe 处理）
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_models_capability_tier ON models(capability_tier)")
    except Exception:
        pass
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_models_use_case ON models(use_case)")
    except Exception:
        pass

    conn.commit()
    conn.close()
