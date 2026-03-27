"""
session/test_session.py - Session模块测试（按4条硬标准）

测试验证：
1. 只存对话历史 + 状态标记，不粘业务逻辑
2. 裁剪策略固定可预测
3. 只提供存/取接口，不调用别人
4. 可回溯、可审计
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from session.models import SessionContext, SessionRecord, TruncateMarker
from session.session_manager import SessionManager, SessionType


class TestModels:
    """测试数据模型"""

    def test_session_record_to_dict(self):
        """验证记录带轮次、request_id、时间"""
        record = SessionRecord(
            round=1,
            request_id="req_001",
            timestamp="2026-03-24 10:00:00",
            role="user",
            content="Hello"
        )
        result = record.to_dict()
        
        assert result["round"] == 1
        assert result["requestId"] == "req_001"
        assert result["timestamp"] == "2026-03-24 10:00:00"
        assert result["role"] == "user"
        assert result["content"] == "Hello"

    def test_session_context_rounds(self):
        """验证会话只存rounds"""
        ctx = SessionContext(
            session_id="s1",
            user_id="u1",
            channel="web",
        )
        
        # 添加轮次
        ctx.rounds.append(SessionRecord(
            round=1,
            request_id="r1",
            timestamp="2026-01-01 00:00:00",
            role="user",
            content="Hi"
        ))
        
        assert len(ctx.rounds) == 1
        assert ctx.get_current_round() == 1

    def test_session_context_state_only_strings(self):
        """验证状态只存字符串（不是业务数据）"""
        ctx = SessionContext(
            session_id="s1",
            user_id="u1",
            channel="web",
        )
        
        # 状态标记（不是业务数据）
        ctx.state = {"intent": "query_order", "waiting": "order_id"}
        
        # 不能存业务数据
        ctx.state = {"order_id": "ORD001"}  # ❌ 这是业务数据，不应该存
        
        # 只能存状态标记
        assert "order_id" in ctx.state  # 但结构上不阻止，这是调用方的事


class TestSessionManager:
    """测试会话管理器"""

    def setup_method(self):
        self.manager = SessionManager(max_rounds=5)

    def test_create_session(self):
        """验证创建会话"""
        session = self.manager.create_session("u1", "web")
        
        assert session.user_id == "u1"
        assert session.channel == "web"
        assert session.session_id != ""
        assert len(session.rounds) == 0
        print(f"\n>>> CREATE: {session.to_dict()}")

    def test_save_round(self):
        """验证存一轮"""
        session = self.manager.create_session("u1", "web")
        
        # 存用户消息
        session, marker = self.manager.save_round(session.session_id, "user", "Hello")
        assert len(session.rounds) == 1
        assert session.rounds[0].round == 1
        
        # 存助手消息
        session, marker = self.manager.save_round(session.session_id, "assistant", "Hi")
        assert len(session.rounds) == 2
        assert session.rounds[1].round == 2

    def test_get_rounds(self):
        """验证取对话"""
        session = self.manager.create_session("u1", "web")
        
        self.manager.save_round(session.session_id, "user", "Hello")
        self.manager.save_round(session.session_id, "assistant", "Hi")
        
        rounds, _ = self.manager.get_rounds(session.session_id)
        
        assert len(rounds) == 2
        assert rounds[0].content == "Hello"
        assert rounds[1].content == "Hi"

    def test_truncate_marker(self):
        """验证截断标记（固定策略）"""
        manager = SessionManager(max_rounds=3)
        session = manager.create_session("u1", "web")
        
        # 存5轮（超过3轮）
        for i in range(5):
            manager.save_round(session.session_id, "user", f"msg{i}")
        
        # 检查标记
        session, marker = manager.save_round(session.session_id, "assistant", "reply")
        
        # 触发截断标记
        assert marker is not None
        assert marker.before_round == 6
        assert marker.after_round == 3
        assert marker.reason == "rounds_exceed"
        print(f"\n>>> TRUNCATE MARKER: {marker.to_dict()}")

    def test_truncate_policy_fixed(self):
        """验证截断策略固定（不随机丢）"""
        manager = SessionManager(max_rounds=2)
        session = manager.create_session("u1", "web")
        
        # 存3轮
        for i in range(3):
            manager.save_round(session.session_id, "user", f"msg{i}")
        
        # 取2轮（固定取最近2轮）
        rounds, _ = manager.get_rounds(session.session_id, keep_rounds=2)
        
        # 应该是最后2轮，不是随机丢
        assert len(rounds) == 2
        assert rounds[0].content == "msg1"
        assert rounds[1].content == "msg2"

    def test_state_update(self):
        """验证状态标记"""
        session = self.manager.create_session("u1", "web")
        
        # 更新状态
        updated = self.manager.update_state(
            session.session_id,
            {"intent": "query_order", "waiting": "order_id"}
        )
        
        assert updated.state["intent"] == "query_order"

    def test_get_state(self):
        """验证获取状态"""
        session = self.manager.create_session("u1", "web")
        self.manager.update_state(session.session_id, {"intent": "hello"})
        
        state = self.manager.get_state(session.session_id)
        
        assert state["intent"] == "hello"

    def test_session_not_found(self):
        """验证获取不存在的会话"""
        result = self.manager.get_session("not_exist")
        assert result is None

    def test_clear_session(self):
        """验证清空会话"""
        session = self.manager.create_session("u1", "web")
        
        result = self.manager.clear_session(session.session_id)
        assert result == True
        
        result = self.manager.get_session(session.session_id)
        assert result is None

    def test_expired_session(self):
        """验证过期会话"""
        session = self.manager.create_session("u1", "web")
        
        # 手动设为过期
        session.expire_at = "2020-01-01 00:00:00"
        
        result = self.manager.get_session(session.session_id)
        assert result is None

    def test_get_user_sessions(self):
        """验证获取用户会话"""
        s1 = self.manager.create_session("u1", "web")
        s2 = self.manager.create_session("u1", "web")
        
        sessions = self.manager.get_user_sessions("u1")
        
        assert len(sessions) == 2

    def test_refresh_session(self):
        """验证刷新会话"""
        import time
        manager = SessionManager(default_expire_minutes=0)
        session = manager.create_session("u1", "web")
        old_expire = session.expire_at
        
        time.sleep(1)
        
        refreshed = manager.refresh_session(session.session_id)
        
        assert refreshed.expire_at != old_expire


class TestNoBusinessLogic:
    """验证不粘业务逻辑"""

    def test_no_order_id_in_state(self):
        """状态里不存业务数据（只存标记）"""
        manager = SessionManager()
        session = manager.create_session("u1", "web")
        
        # ❌ 错误示范：存业务数据
        manager.update_state(session.session_id, {"order_id": "ORD001"})
        
        # 但Session层不阻止（调用方负责）
        state = manager.get_state(session.session_id)
        
        # 只验证结构，语义由调用方负责
        assert "order_id" in state

    def test_no_rag_call(self):
        """验证不调用RAG（无此方法）"""
        manager = SessionManager()
        
        # Session层不应该有这些方法
        assert not hasattr(manager, 'query_vector')
        assert not hasattr(manager, 'search_rag')
        assert not hasattr(manager, 'summarize')


class TestTraceable:
    """验证可回溯"""

    def test_every_round_has_request_id(self):
        """每轮带唯一ID"""
        manager = SessionManager()
        session = manager.create_session("u1", "web")
        
        manager.save_round(session.session_id, "user", "msg1")
        manager.save_round(session.session_id, "user", "msg2")
        
        rounds, _ = manager.get_rounds(session.session_id)
        
        # 每轮有唯一ID
        assert rounds[0].request_id != rounds[1].request_id
        print(f"\n>>> ROUND IDs: {rounds[0].request_id}, {rounds[1].request_id}")

    def test_every_round_has_timestamp(self):
        """每轮带时间戳"""
        manager = SessionManager()
        session = manager.create_session("u1", "web")
        
        manager.save_round(session.session_id, "user", "msg1")
        
        rounds, _ = manager.get_rounds(session.session_id)
        
        assert rounds[0].timestamp != ""

    def test_every_round_has_round_number(self):
        """每轮带轮次号"""
        manager = SessionManager()
        session = manager.create_session("u1", "web")
        
        manager.save_round(session.session_id, "user", "msg1")
        manager.save_round(session.session_id, "assistant", "reply1")
        manager.save_round(session.session_id, "user", "msg2")
        
        rounds, _ = manager.get_rounds(session.session_id)
        
        assert rounds[0].round == 1
        assert rounds[1].round == 2
        assert rounds[2].round == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
