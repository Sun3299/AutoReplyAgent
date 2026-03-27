"""
agent/test_agent.py - Agent模块测试（按6条铁律）

运行方式：
    pytest agent/test_agent.py -v -s

真实用户场景测试：
    pytest agent/test_agent.py::test_real_user_scenarios -v -s
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agent.models import (
    Intent, IntentType, QueryType, ActionType,
    ToolCall, ExecutionTrace,
    AgentConfig, AgentMetrics,
    SessionInfo, AgentInput, AgentOutput,
)
from agent.agent_core import Agent


# ============================================================
# 真实用户场景测试（用print展示）
# ============================================================

def test_real_user_scenarios():
    """
    真实用户场景测试
    
    模拟真实用户提问，展示Agent如何处理
    """
    agent = Agent()
    
    scenarios = [
        {
            "name": "场景1: 用户要查订单",
            "message": "我想查一下我的订单到哪了",
            "session_state": {}
        },
        {
            "name": "场景2: 用户要查订单（已有订单号）",
            "message": "订单123456到哪了",
            "session_state": {"order_id": "123456"}
        },
        {
            "name": "场景3: 用户要退款",
            "message": "我想申请退款",
            "session_state": {}
        },
        {
            "name": "场景4: 用户要退款（已有订单号）",
            "message": "订单ORD001我想退款",
            "session_state": {"order_id": "ORD001"}
        },
        {
            "name": "场景5: 用户问价格",
            "message": "这个产品多少钱",
            "session_state": {}
        },
        {
            "name": "场景6: 用户打招呼",
            "message": "你好",
            "session_state": {}
        },
        {
            "name": "场景7: 用户说太贵了（客户意图-议价）",
            "message": "太贵了，能便宜点吗",
            "session_state": {}
        },
        {
            "name": "场景8: 用户犹豫（客户意图-挽留）",
            "message": "我再考虑考虑",
            "session_state": {}
        },
        {
            "name": "场景9: 用户询问物流",
            "message": "我的快递到哪了",
            "session_state": {}
        },
        {
            "name": "场景10: 未知内容",
            "message": "asdfghjkl123",
            "session_state": {}
        },
    ]
    
    print("\n" + "="*70)
    print("【真实用户场景测试】")
    print("="*70)
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n{'='*70}")
        print(f"{scenario['name']}")
        print(f"{'='*70}")
        
        print(f"\n>>> 用户消息: {scenario['message']}")
        print(f">>> 当前会话状态: {scenario['session_state']}")
        
        # 调用Agent
        session_info = SessionInfo(
            session_id="s1",
            user_id="u1",
            state=scenario["session_state"],
            rounds=[]
        )
        agent_input = AgentInput(
            user_message=scenario["message"],
            session_info=session_info
        )
        output = agent.run(agent_input)
        
        # 输出意图
        print(f"\n<<< 意图识别:")
        print(f"    类型: {output.intent.intent_type.value}")
        if output.intent.query_type:
            print(f"    子类型: {output.intent.query_type.value}")
        if output.intent.action_type:
            print(f"    操作类型: {output.intent.action_type.value}")
        print(f"    置信度: {output.intent.confidence}")
        print(f"    识别理由: {output.intent.reason}")
        
        # 输出执行计划
        print(f"\n<<< 执行计划 (Agent输出的指令):")
        if output.execution_plan:
            for plan in output.execution_plan:
                print(f"    第{plan.step}步: {plan.tool_name}")
                print(f"    理由: {plan.reason}")
                print(f"    参数: {plan.params}")
        else:
            print("    无需调用工具")
        
        # 输出终止信息
        print(f"\n<<< 终止状态:")
        print(f"    是否终止: {output.should_terminate}")
        print(f"    终止原因: {output.terminate_reason}")
        
        # 输出是否需要澄清
        if output.needs_clarify:
            print(f"\n<<< 需要澄清:")
            print(f"    问题: {output.clarify_question}")
        
        print(f"\n<<< 统计指标:")
        m = agent.get_metrics()
        print(f"    总请求: {m.total_requests}, RAG调用: {m.rag_call_count}, 工具调用: {m.tool_call_count}")


def test_single_scenario():
    """单个场景测试"""
    agent = Agent()
    
    print("\n" + "="*70)
    print("【测试】用户：我想查一下我的订单")
    print("="*70)
    
    session_info = SessionInfo(session_id="s1", user_id="u1", state={}, rounds=[])
    agent_input = AgentInput(user_message="我想查一下我的订单", session_info=session_info)
    
    output = agent.run(agent_input)
    
    print(f"\n>>> 用户: 我想查一下我的订单")
    print(f"\n<<< 意图: {output.intent.intent_type.value}")
    print(f"<<< 执行计划: {[p.tool_name for p in output.execution_plan]}")
    print(f"<<< 需要澄清: {output.needs_clarify}")
    if output.needs_clarify:
        print(f"<<< 澄清问题: {output.clarify_question}")


# ============================================================
# 单元测试
# ============================================================

class TestIntentRecognizer:
    def test_query_intent(self):
        from agent.agent_core import IntentRecognizer
        recognizer = IntentRecognizer(AgentConfig())
        intent = recognizer.recognize("check my order", {})
        assert intent.intent_type == IntentType.QUERY

    def test_action_intent(self):
        from agent.agent_core import IntentRecognizer
        recognizer = IntentRecognizer(AgentConfig())
        intent = recognizer.recognize("I want refund", {})
        assert intent.intent_type == IntentType.ACTION


class TestPlanner:
    def test_plan_rag(self):
        from agent.agent_core import Planner
        planner = Planner(AgentConfig())
        output = planner.plan("check order", {})
        assert len(output.execution_plan) > 0
        assert output.execution_plan[0].tool_name == "rag"

    def test_plan_external_direct(self):
        """外部意图直接走工具"""
        from agent.agent_core import Planner
        planner = Planner(AgentConfig())
        # 物流是external，应该直接走工具
        output = planner.plan("我的快递到哪了", {})
        # 外部意图第1层直接返回，不走RAG
        assert output.execution_plan[0].tool_name == "logistics_tool"

    def test_plan_chat_rag(self):
        """闲聊走RAG兜底"""
        from agent.agent_core import Planner
        planner = Planner(AgentConfig())
        output = planner.plan("hello", {})
        # 闲聊终止，但不直接返回（走RAG）
        assert output.should_terminate == True


class TestAgent:
    def test_agent_run(self):
        agent = Agent()
        session_info = SessionInfo(session_id="s1", user_id="u1", state={}, rounds=[])
        output = agent.run(AgentInput(user_message="check order", session_info=session_info))
        assert isinstance(output, AgentOutput)
        assert isinstance(output.intent, Intent)

    def test_metrics(self):
        agent = Agent()
        session_info = SessionInfo(session_id="s1", user_id="u1", state={}, rounds=[])
        agent.run(AgentInput(user_message="hello", session_info=session_info))
        metrics = agent.get_metrics()
        assert metrics.total_requests == 1
        assert metrics.chat_count == 1


class TestConfig:
    def test_custom_config(self):
        config = AgentConfig(max_steps=5, enable_rag=False, enable_tools=True)
        agent = Agent(config)
        assert agent.config.max_steps == 5
        assert agent.config.enable_rag == False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
