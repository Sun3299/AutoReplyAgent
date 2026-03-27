"""
Settings 配置管理
"""

from dataclasses import dataclass
from typing import Optional
import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()


@dataclass
class Settings:
    """全局配置"""
    
    # 环境
    env: str = "dev"
    
    # LLM配置
    llm_provider: str = "minimax"
    llm_api_key: str = ""
    llm_base_url: str = "https://mydamoxing.cn/v1"
    llm_model: str = "MiniMax-M2.7-highspeed"
    
    # RAG配置
    rag_model: str = "BAAI/bge-small-zh-v1.5"
    rag_top_k: int = 3
    
    # 工具配置
    tools_parallel: bool = True
    tools_timeout: int = 30
    
    # Pipeline配置
    pipeline_trace: bool = True
    pipeline_max_retries: int = 3
    
    # 会话配置
    session_ttl: int = 24  # 小时
    session_max_messages: int = 100
    
    # 过滤器配置
    filter_min_length: int = 1
    filter_max_length: int = 2000
    sensitive_words_file: str = "config/sensitive_words.txt"
    
    @classmethod
    def from_env(cls) -> "Settings":
        """从环境变量加载"""
        return cls(
            env=os.getenv("APP_ENV", "dev"),
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            llm_base_url=os.getenv("LLM_BASE_URL", "https://mydamoxing.cn/v1"),
            llm_model=os.getenv("LLM_MODEL", "MiniMax-M2.7-highspeed"),
        )


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """获取全局配置"""
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings
