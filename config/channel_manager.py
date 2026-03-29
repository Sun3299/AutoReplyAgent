"""
渠道配置管理器

根据 channel 加载对应的配置和组件。
"""

import json
import os
from typing import Dict, Any, Optional
from pathlib import Path

# 渠道配置缓存
_channel_configs: Dict[str, Dict[str, Any]] = {}
_loaders: Dict[str, "IntentLoader"] = {}
_retrievers: Dict[str, Any] = {}  # HybridRetriever


def _get_config_path() -> Path:
    """获取渠道配置文件路径"""
    return Path(__file__).parent / "channels.json"


def _load_channel_configs() -> Dict[str, Any]:
    """加载渠道配置"""
    config_path = _get_config_path()
    if not config_path.exists():
        return {"channels": {}, "default": "web"}

    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_channel_config(channel: str) -> Dict[str, Any]:
    """获取指定渠道的配置"""
    global _channel_configs

    if not _channel_configs:
        _channel_configs = _load_channel_configs()

    channels = _channel_configs.get("channels", {})

    if channel not in channels:
        # 如果渠道不存在，返回默认渠道
        default = _channel_configs.get("default", "web")
        return channels.get(default, {})

    return channels.get(channel, {})


def get_default_channel() -> str:
    """获取默认渠道"""
    if not _channel_configs:
        _load_channel_configs()
    return _channel_configs.get("default", "web")


def get_channel_name(channel: str) -> str:
    """获取渠道名称"""
    config = get_channel_config(channel)
    return config.get("name", channel)


def get_intents_path(channel: str) -> Optional[str]:
    """获取指定渠道的意图文件路径"""
    config = get_channel_config(channel)
    path = config.get("intents_path")
    if path:
        # 相对路径转为绝对路径
        return str(Path(__file__).parent.parent / path)
    return None


def get_prompt_path(channel: str) -> Optional[str]:
    """获取指定渠道的提示词文件路径"""
    config = get_channel_config(channel)
    path = config.get("prompt_path")
    if path:
        return str(Path(__file__).parent.parent / path)
    return None


def get_knowledge_path(channel: str) -> Optional[str]:
    """获取指定渠道的知识库文件路径"""
    config = get_channel_config(channel)
    path = config.get("knowledge_path")
    if path:
        return str(Path(__file__).parent.parent / path)
    return None


def get_knowledge_dir(channel: str) -> Optional[str]:
    """获取指定渠道的知识库目录路径"""
    config = get_channel_config(channel)
    path = config.get("knowledge_dir")
    if path:
        full_path = str(Path(__file__).parent.parent / path)
        if os.path.exists(full_path):
            return full_path
    return None


def get_vector_store_path(channel: str) -> Optional[str]:
    """获取指定渠道的向量库目录路径"""
    config = get_channel_config(channel)
    path = config.get("vector_store_path")
    if path:
        full_path = str(Path(__file__).parent.parent / path)
        if os.path.exists(full_path):
            return full_path
    return None


def load_knowledge(channel: str) -> list:
    """
    加载指定渠道的知识库

    支持两种模式：
    1. knowledge_dir/ - 目录，支持 PDF/DOCX/HTML/TXT 等格式
    2. knowledge.txt - 文本文件，每行一条知识

    Returns:
        List of (content, source) tuples
    """
    docs = []

    # 优先从 knowledge_dir 加载
    knowledge_dir = get_knowledge_dir(channel)
    if knowledge_dir:
        from rag.document_loader import DocumentLoaderFactory

        factory = DocumentLoaderFactory()
        try:
            dir_docs = factory.load_directory(knowledge_dir)
            docs.extend(dir_docs)
        except Exception as e:
            print(f"[WARN] 加载知识库目录失败 {knowledge_dir}: {e}")

    # fallback 到 knowledge.txt
    knowledge_path = get_knowledge_path(channel)
    if knowledge_path and os.path.exists(knowledge_path):
        with open(knowledge_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # 格式: 内容|来源
                parts = line.split("|")
                content = parts[0].strip()
                source = parts[1].strip() if len(parts) > 1 else "unknown"
                docs.append((content, source))

    return docs


def get_intent_loader(channel: str):
    """获取指定渠道的 IntentLoader"""
    from agent.intent_loader import IntentLoader

    global _loaders

    if channel not in _loaders:
        intents_path = get_intents_path(channel)
        if intents_path and os.path.exists(intents_path):
            _loaders[channel] = IntentLoader(intents_path)
        else:
            # 如果没有对应渠道的意图文件，创建默认的
            _loaders[channel] = IntentLoader()

    return _loaders[channel]


def get_retriever(channel: str):
    """获取指定渠道的向量检索器"""
    from rag.hybrid_retriever import get_retriever as _get_retriever

    global _retrievers

    if channel not in _retrievers:
        vector_store_path = get_vector_store_path(channel)
        if vector_store_path:
            _retrievers[channel] = _get_retriever(persist_directory=vector_store_path)
        else:
            _retrievers[channel] = _get_retriever()

    return _retrievers[channel]


def reset_loaders():
    """重置所有缓存（用于测试）"""
    global _loaders, _retrievers
    _loaders = {}
    _retrievers = {}


def load_prompt(channel: str) -> str:
    """
    加载指定渠道的 System Prompt

    Args:
        channel: 渠道名称

    Returns:
        Prompt 字符串
    """
    prompt_path = get_prompt_path(channel)
    if prompt_path and os.path.exists(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()

    # Fallback 到默认 prompt
    return "你是一个客服助手。\n回答用户问题时要：\n1. 用自己的话简洁回答，不要列点\n2. 如果有相关知识，结合知识回答，但要用自然的方式\n3. 口语化、亲切、有礼貌"
