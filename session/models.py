"""
session/models.py - 会话数据模型（按4条硬标准设计）

设计原则：
1. 只存对话历史 + 状态标记，不粘业务逻辑
2. 上下文可预测、可复现、可控制
3. 干净解耦，只提供接口，不调用别人
4. 可回溯、可审计

核心结构：
- SessionRecord: 单轮对话记录（带轮次、request_id、时间）
- SessionContext: 会话容器（只存历史 + 状态标记）
"""

# ============================================================
# 基础导入
# ============================================================
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List


# ============================================================
# 核心模型 - 只存对话历史
# ============================================================

@dataclass
class SessionRecord:
    """
    单轮对话记录（不可变）
    
    每条记录带唯一ID和时间，可追溯、可审计。
    不含任何业务数据，只含对话内容。
    
    Attributes:
        round: 轮次编号，从1开始递增
        request_id: 唯一请求ID，用于链路追踪
        timestamp: 时间戳，格式YYYY-MM-DD HH:MM:SS
        role: 角色，user/assistant
        content: 对话内容
    """
    round: int                                        # 轮次（1, 2, 3...）
    request_id: str                                   # 唯一请求ID
    timestamp: str                                    # 时间戳
    role: str                                         # user / assistant
    content: str                                      # 对话内容

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "round": self.round,
            "requestId": self.request_id,
            "timestamp": self.timestamp,
            "role": self.role,
            "content": self.content,
        }


@dataclass
class SessionContext:
    """
    会话容器（只存历史 + 状态标记）
    
    只存两样东西：
    1. rounds: 对话历史（SessionRecord列表）
    2. state: 状态标记（意图、等待输入等）
    
    不存任何业务数据（订单、 商品等）。
    
    Attributes:
        session_id: 会话唯一ID
        user_id: 用户唯一ID
        channel: 来源渠道
        rounds: 轮次列表（按时间正序）
        state: 状态标记字典（非业务数据）
        created_at: 创建时间
        updated_at: 更新时间
        expire_at: 过期时间
    """
    session_id: str                                   # 会话ID
    user_id: str                                      # 用户ID
    channel: str                                      # 来源渠道
    rounds: List[SessionRecord] = field(default_factory=list)  # 轮次列表
    state: Dict[str, str] = field(default_factory=dict)  # 状态标记
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    expire_at: str = ""                               # 过期时间

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于网络传输）"""
        return {
            "sessionId": self.session_id,
            "userId": self.user_id,
            "channel": self.channel,
            "rounds": [r.to_dict() for r in self.rounds],
            "state": self.state,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "expireAt": self.expire_at,
        }

    def get_current_round(self) -> int:
        """获取当前轮次"""
        if not self.rounds:
            return 0
        return self.rounds[-1].round

    def get_last_user_message(self) -> Optional[SessionRecord]:
        """获取最后一条用户消息"""
        for r in reversed(self.rounds):
            if r.role == "user":
                return r
        return None

    def is_expired(self) -> bool:
        """检查是否过期"""
        if not self.expire_at:
            return False
        expire_time = datetime.strptime(self.expire_at, "%Y-%m-%d %H:%M:%S")
        return datetime.now() > expire_time


# ============================================================
# 裁剪标记 - 只标记，不处理
# ============================================================

@dataclass
class TruncateMarker:
    """
    截断标记（告诉调用方需要裁剪）
    
    Session层只负责标记"需要裁剪"，
    谁调用Session，谁负责实际处理（调用LLM生成摘要等）。
    这样保持解耦。
    
    Attributes:
        before_round: 截断前的轮次
        after_round: 截断后的轮次
        reason: 截断原因（rounds_exceed / tokens_exceed）
    """
    before_round: int
    after_round: int
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beforeRound": self.before_round,
            "afterRound": self.after_round,
            "reason": self.reason,
        }
