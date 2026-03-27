"""
Output 回复策略

不同场景使用不同的回复策略。
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any

from .synthesizer import OutputContext, OutputResult, OutputFormat


class ReplyStrategy(ABC):
    """
    回复策略基类
    
    定义不同场景的回复策略接口。
    """
    
    @abstractmethod
    def synthesize(self, context: OutputContext) -> OutputResult:
        """
        根据上下文合成回复
        
        Args:
            context: 输出上下文
            
        Returns:
            OutputResult: 合成后的结果
        """
        pass


class DirectStrategy(ReplyStrategy):
    """
    直接回复策略
    
    适用于：闲聊、简单问答。
    直接使用 LLM 输出作为回复。
    """
    
    def synthesize(self, context: OutputContext) -> OutputResult:
        """直接返回 LLM 输出"""
        return OutputResult(
            content=context.llm_output or "抱歉，我无法回答这个问题。",
            format=OutputFormat.TEXT,
            source="direct"
        )


class RagFirstStrategy(ReplyStrategy):
    """
    RAG 优先策略
    
    适用于：知识问答。
    优先使用 RAG 检索结果，如果不足再用 LLM 补充。
    """
    
    def synthesize(self, context: OutputContext) -> OutputResult:
        """RAG 优先"""
        if context.rag_results:
            contents = [f"根据查询结果："]
            for i, result in enumerate(context.rag_results, 1):
                contents.append(f"{i}. {result}")
            
            content = "\n".join(contents)
            
            # 如果有 LLM 补充
            if context.llm_output:
                content += f"\n\n补充说明：{context.llm_output}"
            
            return OutputResult(
                content=content,
                format=OutputFormat.LIST,
                source="rag_first"
            )
        
        # 没有 RAG 结果，回退到直接回复
        return OutputResult(
            content=context.llm_output or "抱歉，没有找到相关信息。",
            format=OutputFormat.TEXT,
            source="rag_fallback"
        )


class ToolFirstStrategy(ReplyStrategy):
    """
    工具优先策略
    
    适用于：业务查询（订单、物流等）。
    优先使用工具调用结果。
    """
    
    def synthesize(self, context: OutputContext) -> OutputResult:
        """工具结果优先"""
        if context.tool_results:
            lines = []
            
            for result in context.tool_results:
                if isinstance(result, dict):
                    if result.get("success"):
                        data = result.get("data", {})
                        if isinstance(data, dict):
                            # 格式化显示
                            for key, value in data.items():
                                lines.append(f"{key}: {value}")
                        else:
                            lines.append(str(data))
                    else:
                        lines.append(f"查询失败: {result.get('error', '未知错误')}")
                else:
                    lines.append(str(result))
            
            return OutputResult(
                content="\n".join(lines),
                format=OutputFormat.TEXT,
                source="tool"
            )
        
        # 没有工具结果
        return OutputResult(
            content="无法完成查询，请稍后重试。",
            format=OutputFormat.TEXT,
            source="tool_fallback"
        )


class HybridStrategy(ReplyStrategy):
    """
    混合策略
    
    适用于：复杂场景。
    综合 RAG + 工具 + LLM 的结果。
    """
    
    def synthesize(self, context: OutputContext) -> OutputResult:
        """综合多种来源"""
        parts = []
        
        # 1. RAG 结果
        if context.rag_results:
            parts.append("【知识库参考】")
            for i, result in enumerate(context.rag_results, 1):
                parts.append(f"{i}. {result}")
        
        # 2. 工具结果
        if context.tool_results:
            parts.append("\n【查询结果】")
            for result in context.tool_results:
                if isinstance(result, dict) and result.get("success"):
                    data = result.get("data", {})
                    if isinstance(data, dict):
                        for key, value in data.items():
                            parts.append(f"{key}: {value}")
        
        # 3. LLM 补充
        if context.llm_output:
            parts.append(f"\n【智能补充】\n{context.llm_output}")
        
        if not parts:
            return OutputResult(
                content="抱歉，无法生成回复。",
                format=OutputFormat.TEXT,
                source="fallback"
            )
        
        return OutputResult(
            content="\n".join(parts),
            format=OutputFormat.MARKDOWN,
            source="hybrid"
        )
