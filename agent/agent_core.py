"""
agent/agent_core.py - Agent核心逻辑

完全基于 intent_loader.decide_route() 的路由结果来决策。

路由类型 (来自 decide_route):
- rag: 走 RAG 检索
- external: 走外部工具
- clarify: 需要澄清
- ambiguous: 多意图歧义
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid

from .models import (
    ToolCall,
    ExecutionTrace,
    AgentConfig,
    AgentMetrics,
    SessionInfo,
    AgentInput,
    AgentOutput,
    AgentRecommendation,
)
from .intent_loader import get_intent_loader, IntentMatch


class Planner:
    """规划器 - 基于 intent_loader 的路由结果"""

    def __init__(self, config: AgentConfig, channel: str = "web"):
        self.config = config
        self.channel = channel
        self.loader = get_intent_loader(channel)

    def plan(self, user_message: str, session_state: Dict[str, str]) -> AgentOutput:
        """
        生成执行计划

        路由逻辑完全来自 intent_loader.decide_route()
        """
        trace = ExecutionTrace()

        # 调用 intent_loader 决定路由
        route_result = self.loader.decide_route(user_message, session_state)

        print(f"[AGENT DEBUG] route_result: {route_result}", flush=True)

        route = route_result.get("route", "external")
        confidence = route_result.get("confidence", 0.0)
        intent_match = route_result.get("intent")
        reason = route_result.get("reason", "")

        plan = []
        should_terminate = False
        terminate_reason = ""
        needs_clarify = route_result.get("need_clarify", False)
        clarify_question = route_result.get("reason", "")

        # P2优化: 置信度门限过滤
        # 置信度太低时，即使路由到RAG也当闲聊处理，避免低质量检索
        LOW_CONFIDENCE_THRESHOLD = -0.3
        if route == "rag" and confidence < LOW_CONFIDENCE_THRESHOLD:
            print(
                f"[AGENT DEBUG] RAG置信度{confidence:.2f}低于阈值{LOW_CONFIDENCE_THRESHOLD}，降级为chat"
            )
            route = "chat"  # 降级为chat
            # plan = []  # 清空plan，不执行RAG

        # 根据路由类型生成执行计划（完整的 if/elif/else 链）
        if route == "clarify":
            # 需要澄清 - 不终止，让 LLM 帮助用户明确
            should_terminate = False
            needs_clarify = True
            trace.add_call("_clarify", clarify_question, {})

        elif route == "ambiguous":
            # 多意图歧义 - 不终止，让 LLM 判断用户意图
            should_terminate = False
            needs_clarify = True
            trace.add_call("_ambiguous", clarify_question, {})

        elif intent_match and intent_match.intent_key == "chat":
            # 如果匹配的是 chat 意图，做RAG作为背景知识（P1优化）
            trace.add_call("chat", "Chat意图，RAG查背景知识+LLM回复", {})
            plan.append(
                ToolCall(
                    step=1,
                    tool_name="rag",
                    reason="Chat意图背景知识查询",
                    params={"query": user_message, "optional": True},
                )
            )

        elif route == "rag":
            # 走 RAG 检索
            plan.append(
                ToolCall(
                    step=1,
                    tool_name="rag",
                    reason=f"RAG路由: {reason} (置信度:{confidence:.2f})",
                    params={"query": user_message},
                )
            )
            trace.add_call("rag", f"RAG检索 [消息:{user_message[:20]}...]", {})

        elif route == "external":
            # 走外部工具或外部搜索
            if intent_match and intent_match.intent_key.startswith("query_logistics"):
                plan.append(
                    ToolCall(
                        step=1,
                        tool_name="logistics_tool",
                        reason=f"外部工具: {reason}",
                        params={"query": user_message},
                    )
                )
                trace.add_call("logistics_tool", "物流查询", {})
            else:
                plan.append(
                    ToolCall(
                        step=1,
                        tool_name="external_search",
                        reason=f"外部搜索兜底: {reason}",
                        params={"query": user_message},
                    )
                )
                trace.add_call("external_search", "外部搜索", {})

        # elif route == "chat":
        #     # 无意图/低置信，不执行工具，但让 LLM 生成回复（不终止）
        #     should_terminate = False
        #     terminate_reason = ""

        else:
            # 默认走 RAG 兜底
            plan.append(
                ToolCall(
                    step=1,
                    tool_name="rag",
                    reason=f"默认RAG兜底",
                    params={"query": user_message},
                )
            )
            trace.add_call("rag", "默认RAG检索", {})

        # 构建 Intent 对象（兼容旧接口，但用 intent_match 的数据）
        intent = _build_intent(intent_match, confidence, reason, route)

        return AgentOutput(
            intent=intent,
            execution_plan=plan,
            execution_trace=trace,
            needs_clarify=needs_clarify,
            clarify_question=clarify_question,
            should_terminate=should_terminate,
            terminate_reason=terminate_reason,
        )


def _build_intent(
    intent_match: Optional[IntentMatch], confidence: float, reason: str, route: str
):
    """
    根据 intent_match 构建 Intent 对象

    兼容旧接口，但数据来自 intent_loader
    """
    # 复用 models.py 里的 Intent 定义（从 models 导入）
    from .models import Intent

    if intent_match is None:
        return Intent(
            intent_type="unknown",
            confidence=confidence,
            reason=reason,
            knowledge_type="unknown",
        )

    intent_key = intent_match.intent_key
    knowledge_type = intent_match.knowledge_type

    # 判断 intent_type
    if route == "clarify":
        intent_type = "clarify"
    elif route == "ambiguous":
        intent_type = "unknown"
    elif route == "rag":
        intent_type = "query"
    elif route == "external":
        if intent_key.startswith("query_"):
            intent_type = "query"
        elif intent_key.startswith("action_"):
            intent_type = "action"
        else:
            intent_type = "chat"
    else:
        intent_type = "unknown"

    # 判断 query_type / action_type
    query_type = None
    action_type = None

    if intent_key.startswith("query_"):
        query_type = intent_key.replace("query_", "")
    elif intent_key.startswith("action_"):
        action_type = intent_key.replace("action_", "")

    return Intent(
        intent_type=intent_type,
        query_type=query_type,
        action_type=action_type,
        confidence=confidence,
        reason=reason,
        knowledge_type=knowledge_type,
    )


class Agent:
    """Agent核心"""

    def __init__(self, config: Optional[AgentConfig] = None, channel: str = "web"):
        self.config = config or AgentConfig()
        self.channel = channel
        self.planner = Planner(self.config, channel)
        self.metrics = AgentMetrics()

    def run(self, agent_input: AgentInput) -> AgentOutput:
        """运行Agent"""
        self.metrics.record_request()

        # 确保 channel 一致
        if agent_input.channel:
            self.channel = agent_input.channel
            self.planner = Planner(self.config, self.channel)
            self.planner.loader = get_intent_loader(self.channel)

        output = self.planner.plan(
            user_message=agent_input.user_message,
            session_state=agent_input.session_info.state,
        )

        # 生成推荐决策
        recommendation = self._decide_recommendation(
            intent=output.intent,
            user_context={
                "user_tier": agent_input.session_info.state.get("user_tier", "normal")
            },
            session_history=agent_input.session_info.rounds,
        )
        # output.recommendation = recommendation

        self._record_metrics(output)
        return output

    def _decide_recommendation(
        self,
        intent,
        user_context: Dict[str, Any],
        session_history: List[Any],
    ) -> AgentRecommendation:
        """
        决定是否推荐
        """
        # 投诉/退款 → 转人工
        action_type = getattr(intent, "action_type", None)
        if action_type == "refund":
            return AgentRecommendation(
                action="transfer", confidence=0.9, reason="退款需求转人工处理"
            )

        # 用户等级和置信度
        user_tier = user_context.get("user_tier", "normal")
        confidence = getattr(intent, "confidence", 0.0)

        if user_tier == "vip" and confidence > 0.8:
            return AgentRecommendation(
                action="recommend",
                product_id="VIP_PRODUCT",
                product_name="VIP专属套餐",
                reason="您是我们的VIP用户，专属推荐",
                confidence=confidence,
            )

        # 新用户引导
        if user_tier == "normal" and len(session_history) <= 1:
            return AgentRecommendation(
                action="recommend",
                product_id="STARTER_PRODUCT",
                product_name="新人专属套餐",
                reason="新用户首购优惠",
                confidence=0.8,
            )

        return AgentRecommendation(action="none", confidence=0.0)

    def _record_metrics(self, output: AgentOutput):
        intent_type = getattr(output.intent, "intent_type", "unknown")

        if intent_type == "clarify":
            self.metrics.record_clarify()
        elif intent_type == "query":
            for plan in output.execution_plan:
                if plan.tool_name == "rag":
                    self.metrics.record_rag()
                elif plan.tool_name not in [
                    "_rag_confidence_check",
                    "_clarify",
                    "_ambiguous",
                ]:
                    self.metrics.record_tool_call(True)

    def get_metrics(self) -> AgentMetrics:
        return self.metrics
