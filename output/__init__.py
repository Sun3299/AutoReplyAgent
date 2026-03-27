"""
Output 合成层模块

负责将 RAG 结果、工具调用结果、LLM 输出等合成为最终用户回复。

核心功能：
1. 多源整合：RAG + 工具 + 对话历史
2. 回复策略：根据场景选择不同回复方式
3. 格式控制：控制回复格式（简洁/详细/列表等）
"""

from .synthesizer import (
    OutputSynthesizer,
    get_synthesizer,
    OutputContext,
    OutputResult,
    OutputFormat,
)
from .strategy import (
    ReplyStrategy,
    DirectStrategy,      # 直接回复
    RagFirstStrategy,     # RAG 优先
    ToolFirstStrategy,     # 工具优先
    HybridStrategy,        # 混合策略
)

__all__ = [
    # 合成器
    "OutputSynthesizer",
    "get_synthesizer",
    "OutputContext",
    "OutputResult",
    "OutputFormat",
    
    # 策略
    "ReplyStrategy",
    "DirectStrategy",
    "RagFirstStrategy",
    "ToolFirstStrategy",
    "HybridStrategy",
]
