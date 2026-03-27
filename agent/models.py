"""
agent/models.py - Agent模块数据模型（按6条铁律）

铁律1: 只做规划+调用+结果聚合，不自己生成答案
铁律2: 调用可解释、可复现、可打断、可降级
铁律3: 有明确终止条件，最大调用次数限制
铁律4: 不存业务状态，只存推理轨迹
铁律5: 逻辑模块化、可插拔
铁律6: 可评测、可量化

核心结构：
- ToolCall: 工具调用记录（可解释、可追溯）
- ExecutionTrace: 执行轨迹（每一步都记录）
- AgentConfig: 配置（可插拔）
- AgentMetrics: 统计指标（可量化）
"""

# ============================================================
# 基础导入
# ============================================================
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


# ============================================================
# 工具调用（铁律2: 可解释、可追溯）
# ============================================================

@dataclass
class ToolCall:
    """
    工具调用记录
    
    每次工具调用都记录，可解释、可追溯。
    相同输入产生相同调用序列（可复现）。
    
    Attributes:
        step: 第几步
        tool_name: 工具名
        reason: 调用理由（可解释）
        params: 调用参数
        result: 调用结果（由执行层填入）
        status: 调用状态 pending/success/failed
    """
    step: int                                        # 第几步
    tool_name: str                                   # 工具名
    reason: str                                      # 调用理由
    params: Dict[str, Any] = field(default_factory=dict)  # 参数
    result: Optional[Any] = None                      # 结果
    status: str = "pending"                           # pending/success/failed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "toolName": self.tool_name,
            "reason": self.reason,
            "params": self.params,
            "result": str(self.result) if self.result else None,
            "status": self.status,
        }


# ============================================================
# 意图（只做判断）
# ============================================================

@dataclass
class Intent:
    """
    意图识别结果
    
    只做判断，不执行。
    knowledge_type: internal(内部RAG) / external(外部工具) / both(两者) / unknown(未知)
    intent_type: query / action / chat / clarify / unknown
    """
    intent_type: str = "unknown"
    query_type: Optional[str] = None
    action_type: Optional[str] = None
    confidence: float = 1.0
    reason: str = ""
    knowledge_type: str = "internal"

    def to_dict(self) -> Dict[str, Any]:
        result = {"intentType": self.intent_type}
        if self.query_type:
            result["queryType"] = self.query_type
        if self.action_type:
            result["actionType"] = self.action_type
        result["confidence"] = self.confidence
        result["reason"] = self.reason
        result["knowledgeType"] = self.knowledge_type
        return result


# ============================================================
# 执行轨迹（铁律4: 只存推理轨迹）
# ============================================================

@dataclass
class ExecutionTrace:
    """
    执行轨迹
    
    只存推理过程，不存业务状态。
    """
    tool_calls: List[ToolCall] = field(default_factory=list)
    current_step: int = 0
    terminated: bool = False
    terminate_reason: str = ""

    def add_call(self, tool_name: str, reason: str, params: Dict[str, Any]):
        """添加一个工具调用"""
        self.current_step += 1
        self.tool_calls.append(ToolCall(
            step=self.current_step,
            tool_name=tool_name,
            reason=reason,
            params=params,
        ))

    def mark_success(self, step: int, result: Any):
        """标记调用成功"""
        for call in self.tool_calls:
            if call.step == step:
                call.result = result
                call.status = "success"
                break

    def mark_failed(self, step: int, error: str):
        """标记调用失败"""
        for call in self.tool_calls:
            if call.step == step:
                call.result = error
                call.status = "failed"
                break

    def terminate(self, reason: str):
        """终止执行"""
        self.terminated = True
        self.terminate_reason = reason

    def to_dict(self) -> Dict[str, Any]:
        return {
            "toolCalls": [c.to_dict() for c in self.tool_calls],
            "currentStep": self.current_step,
            "terminated": self.terminated,
            "terminateReason": self.terminate_reason,
        }


# ============================================================
# Agent配置（铁律5: 逻辑模块化）
# ============================================================

@dataclass
class AgentConfig:
    """
    Agent配置
    
    全部可配置，不硬编码。
    """
    max_steps: int = 3                              # 铁律3: 最大调用次数
    enable_rag: bool = True                         # 是否启用RAG
    enable_tools: bool = True                       # 是否启用工具
    enable_chat: bool = True                       # 是否启用闲聊
    tool_list: List[str] = field(default_factory=lambda: [
        "order_query_tool",
        "logistics_query_tool",
        "refund_tool",
        "cancel_tool",
    ])
    rag_fallback: bool = True                      # 工具失败是否降级RAG

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'AgentConfig':
        return cls(**{k: v for k, v in config.items() if k in cls.__annotations__})


# ============================================================
# 统计指标（铁律6: 可量化）
# ============================================================

@dataclass
class AgentMetrics:
    """
    统计指标
    
    可量化Agent表现。
    """
    total_requests: int = 0
    tool_call_count: int = 0
    tool_call_success: int = 0
    tool_call_failed: int = 0
    rag_call_count: int = 0
    chat_count: int = 0
    clarify_count: int = 0
    unknown_count: int = 0

    def record_request(self):
        self.total_requests += 1

    def record_tool_call(self, success: bool):
        self.tool_call_count += 1
        if success:
            self.tool_call_success += 1
        else:
            self.tool_call_failed += 1

    def record_rag(self):
        self.rag_call_count += 1

    def record_chat(self):
        self.chat_count += 1

    def record_clarify(self):
        self.clarify_count += 1

    def record_unknown(self):
        self.unknown_count += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "totalRequests": self.total_requests,
            "toolCallCount": self.tool_call_count,
            "toolCallSuccess": self.tool_call_success,
            "toolCallFailed": self.tool_call_failed,
            "ragCallCount": self.rag_call_count,
            "chatCount": self.chat_count,
            "clarifyCount": self.clarify_count,
            "unknownCount": self.unknown_count,
            "toolSuccessRate": self.tool_call_success / self.tool_call_count if self.tool_call_count > 0 else 0,
        }


# ============================================================
# 输入输出
# ============================================================

@dataclass
class AgentRecommendation:
    """Agent 结构化推荐"""
    action: str  # "none" | "recommend" | "follow_up" | "transfer"
    product_id: Optional[str] = None  # 推荐商品ID
    product_name: Optional[str] = None  # 推荐商品名称
    reason: Optional[str] = None  # 推荐理由
    confidence: float = 0.0  # 置信度 0-1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "reason": self.reason,
            "confidence": self.confidence,
        }


@dataclass
class SessionInfo:
    """会话信息（从Session层获取，只读）"""
    session_id: str
    user_id: str
    state: Dict[str, str] = field(default_factory=dict)
    rounds: List[Any] = field(default_factory=list)


@dataclass
class AgentInput:
    """Agent输入"""
    user_message: str
    session_info: SessionInfo
    channel: str = "web"


@dataclass
class AgentOutput:
    """
    Agent输出
    
    只包含规划，不包含执行结果。
    执行结果由执行层填充。
    """
    intent: Intent                                    # 意图
    execution_plan: List[ToolCall] = field(default_factory=list)  # 规划
    execution_trace: ExecutionTrace = field(default_factory=ExecutionTrace)  # 轨迹
    needs_clarify: bool = False
    clarify_question: str = ""
    should_terminate: bool = False
    terminate_reason: str = ""
    recommendation: Optional[AgentRecommendation] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "intent": self.intent.to_dict(),
            "executionPlan": [p.to_dict() for p in self.execution_plan],
            "executionTrace": self.execution_trace.to_dict(),
            "needsClarify": self.needs_clarify,
            "clarifyQuestion": self.clarify_question,
            "shouldTerminate": self.should_terminate,
            "terminateReason": self.terminate_reason,
        }
        if self.recommendation:
            result["recommendation"] = self.recommendation.to_dict()
        return result
