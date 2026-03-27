"""
Output 合成器

将 RAG 结果、工具调用结果、LLM 输出合成为最终用户回复。
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

from output.filters import SensitiveWordFilter, LengthValidator
from config.settings import get_settings


class OutputFormat(Enum):
    """输出格式枚举"""
    TEXT = "text"           # 纯文本
    LIST = "list"           # 列表
    TABLE = "table"         # 表格
    JSON = "json"          # JSON
    MARKDOWN = "markdown"   # Markdown


@dataclass
class OutputContext:
    """
    输出上下文
    
    包含合成回复所需的所有信息。
    
    Attributes:
        rag_results: RAG 检索结果
        tool_results: 工具调用结果
        llm_output: LLM 原始输出
        intent: 识别到的意图
        confidence: 置信度
        session_state: 会话状态
    """
    rag_results: List[str] = field(default_factory=list)   # RAG 结果
    tool_results: List[Dict[str, Any]] = field(default_factory=list)  # 工具结果
    llm_output: str = ""                              # LLM 输出
    intent: str = ""                                 # 意图
    confidence: float = 0.0                          # 置信度
    session_state: Dict[str, Any] = field(default_factory=dict)  # 会话状态


@dataclass
class OutputResult:
    """
    输出结果
    
    合成后的最终回复。
    
    Attributes:
        content: 回复内容
        format: 输出格式
        source: 来源（rag/tool/llm）
        metadata: 额外信息
    """
    content: str                              # 回复内容
    format: OutputFormat = OutputFormat.TEXT  # 格式
    source: str = "unknown"                  # 来源
    metadata: Dict[str, Any] = field(default_factory=dict)  # 额外信息


class OutputSynthesizer:
    """
    Output 合成器
    
    根据上下文合成最终回复。
    
    使用示例：
        synthesizer = OutputSynthesizer()
        
        context = OutputContext(
            rag_results=["根据退货政策，7天内..."],
            intent="query_refund"
        )
        
        result = synthesizer.synthesize(context)
        print(result.content)
    """
    
    def __init__(self):
        """初始化合成器"""
        self._strategies: Dict[str, Any] = {}
        settings = get_settings()
        self._word_filter = SensitiveWordFilter()
        self._length_validator = LengthValidator(
            min_length=settings.filter_min_length,
            max_length=settings.filter_max_length
        )
    
    def register_strategy(self, name: str, strategy: Any):
        """
        注册策略
        
        Args:
            name: 策略名称
            strategy: 策略实例
        """
        self._strategies[name] = strategy
    
    def synthesize(self, context: OutputContext) -> OutputResult:
        """
        合成回复
        
        根据上下文中的信息，选择合适的策略合成回复。
        
        优先级：LLM输出 > 工具结果 > RAG结果 > 默认回复
        
        Args:
            context: 输出上下文
            
        Returns:
            OutputResult: 合成后的结果
        """
        # 策略1：LLM 输出优先（自然对话）
        if context.llm_output:
            result = OutputResult(
                content=context.llm_output,
                format=OutputFormat.TEXT,
                source="llm"
            )
            return self._apply_filters(result)
        
        # 策略2：工具结果次之
        if context.tool_results:
            result = self._synthesize_from_tools(context)
            return self._apply_filters(result)
        
        # 策略3：RAG 结果
        if context.rag_results:
            result = self._synthesize_from_rag(context)
            return self._apply_filters(result)
        
        # 策略4：默认回复
        return OutputResult(
            content="抱歉，我无法回答这个问题。",
            format=OutputFormat.TEXT,
            source="fallback"
        )
    
    def _apply_filters(self, result: OutputResult) -> OutputResult:
        """应用质量过滤器"""
        # 长度验证
        is_valid, error_msg = self._length_validator.validate(result.content)
        if not is_valid:
            return OutputResult(
                content="抱歉，该回答无法提供。",
                format=result.format,
                source=result.source,
                metadata={"filter_reason": error_msg}
            )
        
        # 敏感词过滤
        filtered_content, was_modified = self._word_filter.filter(result.content)
        result.content = filtered_content
        if was_modified:
            result.metadata["word_filtered"] = True
        
        return result
    
    def _synthesize_from_tools(self, context: OutputContext) -> OutputResult:
        """从工具结果合成"""
        # 合并工具结果
        contents = []
        for result in context.tool_results:
            if isinstance(result, dict):
                if result.get("success"):
                    contents.append(str(result.get("data", "")))
                else:
                    contents.append(f"查询失败: {result.get('error', '未知错误')}")
            else:
                contents.append(str(result))
        
        content = "\n".join(contents)
        
        return OutputResult(
            content=content,
            format=OutputFormat.TEXT,
            source="tool"
        )
    
    def _synthesize_from_rag(self, context: OutputContext) -> OutputResult:
        """从 RAG 结果合成"""
        contents = []
        for i, result in enumerate(context.rag_results, 1):
            contents.append(f"{i}. {result}")
        
        content = "\n".join(contents)
        
        return OutputResult(
            content=content,
            format=OutputFormat.LIST,
            source="rag"
        )


# 全局单例
_synthesizer: Optional[OutputSynthesizer] = None


def get_synthesizer() -> OutputSynthesizer:
    """获取全局合成器实例"""
    global _synthesizer
    if _synthesizer is None:
        _synthesizer = OutputSynthesizer()
    return _synthesizer
