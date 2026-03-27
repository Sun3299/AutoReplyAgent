"""
LLM Step - LLM生成步骤

使用 LLM Fallback 链生成响应。

输入：
    - ctx.request: 用户消息
    - ctx.get("rag_results"): RAG 检索结果
    - ctx.get("tool_results"): 工具执行结果

输出：
    - ctx.set("llm_response", response.content): LLM 响应内容
    - ctx.set("llm_model_used", model_name): 实际使用的模型
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any, TYPE_CHECKING
import time

from pipeline.step import Step, StepResult, StepType
from llm.base import Message, MessageRole, LLMConfig
from llm.fallback import ModelFallbackChain

if TYPE_CHECKING:
    from pipeline.orchestrator import PipelineContext


class LlmStep(Step):
    """
    LLM 生成步骤
    
    负责：
    1. 构建 prompt
    2. 调用 LLM Fallback 链
    3. 记录使用的模型
    
    使用示例：
        step = LlmStep()
        result = step.execute(ctx)
    """
    
    def __init__(
        self,
        fallback_chain: Optional[ModelFallbackChain] = None,
        default_config: Optional[LLMConfig] = None,
    ):
        """
        初始化 LLM 步骤
        
        Args:
            fallback_chain: LLM Fallback 链，默认创建 MiniMax → Claude → GPT-3.5 链
            default_config: 默认 LLM 配置
        """
        super().__init__("llm_step", StepType.LLM, optional=False, timeout=60)
        self._fallback_chain = fallback_chain
        self._default_config = default_config or LLMConfig()
    
    @property
    def fallback_chain(self) -> ModelFallbackChain:
        """获取 Fallback 链"""
        if self._fallback_chain is None:
            # 延迟创建，避免循环导入
            from llm.providers import MiniMaxProvider, MockLLMProvider
            from llm.claude import ClaudeProvider
            from llm.gpt35 import GPT35Provider
            from config.settings import get_settings

            settings = get_settings()
            api_key = settings.llm_api_key or "mock"
            base_url = settings.llm_base_url or "https://mydamoxing.cn/v1"
            model = settings.llm_model or "MiniMax-M2.7-highspeed"

            # 使用真实配置的 MiniMax，Mock 其他作为 fallback
            self._fallback_chain = ModelFallbackChain([
                MiniMaxProvider(api_key=api_key, base_url=base_url, model=model),
                # MockClaudeProvider(api_key="mock") as fallback
                MockLLMProvider(response_content="Claude 暂时不可用"),
            ])
        return self._fallback_chain
    
    def _do_execute(self, ctx: 'PipelineContext') -> StepResult:
        """
        执行 LLM 生成
        
        Args:
            ctx: Pipeline上下文
            
        Returns:
            StepResult: 执行结果
        """
        start_time = time.time()
        
        try:
            # 检查是否应该终止
            if ctx.get("should_terminate"):
                return StepResult(
                    success=True,
                    data={"message": "Skipped due to termination"},
                    step_name=self.name,
                    step_type=self.step_type.value,
                    duration=time.time() - start_time,
                    metadata={
                        "skipped": True,
                        "reason": ctx.get("terminate_reason", "Unknown"),
                        "duration_ms": int((time.time() - start_time) * 1000),
                    }
                )
            
            # 构建消息
            messages = self._build_messages(ctx)
            
            # 调用 LLM（不传 config，让 provider 使用自己的默认配置）
            response = self.fallback_chain.chat(messages, None)
            
            # 提取模型信息
            model_used = "unknown"
            if response.metadata:
                model_used = response.metadata.get("model_used", "unknown")
            
            # 检查是否成功
            if response.error:
                duration = time.time() - start_time
                return StepResult(
                    success=False,
                    error=f"LLM failed: {response.error}",
                    step_name=self.name,
                    step_type=self.step_type.value,
                    duration=duration,
                    metadata={
                        "model_used": model_used,
                        "duration_ms": int(duration * 1000),
                    }
                )
            
            # 设置到上下文
            ctx.set("llm_response", response.content)
            ctx.set("llm_model_used", model_used)
            
            duration = time.time() - start_time
            
            return StepResult(
                success=True,
                data={
                    "content": response.content,
                    "model_used": model_used,
                    "usage": response.usage,
                },
                step_name=self.name,
                step_type=self.step_type.value,
                duration=duration,
                metadata={
                    "model_used": model_used,
                    "duration_ms": int(duration * 1000),
                }
            )
            
        except Exception as e:
            duration = time.time() - start_time
            return StepResult(
                success=False,
                error=f"LlmStep failed: {type(e).__name__}: {str(e)}",
                step_name=self.name,
                step_type=self.step_type.value,
                duration=duration,
                metadata={
                    "error_type": type(e).__name__,
                    "duration_ms": int(duration * 1000),
                }
            )
    
    def _build_messages(self, ctx: 'PipelineContext') -> List[Message]:
        """
        构建消息列表
        
        Args:
            ctx: Pipeline上下文
            
        Returns:
            消息列表
        """
        messages: List[Message] = []
        
        # 添加系统消息
        system_prompt = ctx.get("system_prompt")
        if system_prompt:
            prompt = system_prompt
        else:
            prompt = """你是一个客服助手。
回答用户问题时要：
1. 用自己的话简洁回答，不要列点
2. 如果有相关知识，结合知识回答，但要用自然的方式，不要说"根据知识..." 
3. 口语化、亲切、有礼貌"""
        
        # 添加商品信息（从 extension.item_info 获取）
        extension = ctx.get("extension", {})
        item_info = extension.get("item_info", "") if isinstance(extension, dict) else ""
        if item_info:
            prompt = f"{prompt}\n\n【当前商品信息】\n{item_info}"
        
        messages.append(Message(role=MessageRole.SYSTEM, content=prompt))
        
        # 添加 RAG 结果作为参考信息（不要直接返回列表）
        rag_results = ctx.get("rag_results", [])
        if rag_results:
            rag_context = self._format_rag_results(rag_results)
            messages.append(Message(
                role=MessageRole.USER,
                content=f"【用户可能想知道的信息(来源RAG)】\n{rag_context}\n\n请根据以上信息回答。如果有明确的标准问答，直接用标准答案回答，不要重复提问，用自然的方式回复，不要直接复述列表。"
            ))
        
        # 添加工具结果作为上下文
        tool_results = ctx.get("tool_results", [])
        if tool_results:
            tool_context = self._format_tool_results(tool_results)
            messages.append(Message(
                role=MessageRole.SYSTEM,
                content=f"【工具查询结果】\n{tool_context}"
            ))
        
        # 添加历史消息（如果有）
        history = ctx.get("history_messages", [])
        for hist_msg in history:
            role = MessageRole.USER if hist_msg.get("role") == "user" else MessageRole.ASSISTANT
            messages.append(Message(
                role=role,
                content=hist_msg.get("content", "")
            ))
        
        # 添加用户消息
        messages.append(Message(
            role=MessageRole.USER,
            content=ctx.request
        ))
        
        return messages
    
    def _format_rag_results(self, rag_results: List[Any]) -> str:
        """格式化 RAG 结果为自然段落"""
        if not rag_results:
            return "没有找到相关信息"
        
        parts = []
        for result in rag_results:
            if isinstance(result, str):
                parts.append(result)
            elif isinstance(result, dict):
                parts.append(result.get("content", str(result)))
            else:
                parts.append(str(result))
        
        # 用句子连接，不用列表
        return "、".join(parts)
    
    def _format_tool_results(self, tool_results: List[Dict[str, Any]]) -> str:
        """格式化工具结果"""
        if not tool_results:
            return "无工具查询结果"
        
        formatted = []
        for result in tool_results:
            tool_name = result.get("tool_name", "unknown")
            success = result.get("success", False)
            data = result.get("data")
            error = result.get("error", "")
            
            if success:
                content = str(data) if data else "无数据"
                formatted.append(f"【{tool_name}】查询成功: {content}")
            else:
                formatted.append(f"【{tool_name}】查询失败: {error}")
        
        return "\n".join(formatted)
