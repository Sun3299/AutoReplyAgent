"""
session/session_manager.py - 会话管理器（按4条硬标准设计）

设计原则：
1. 无状态可水平扩展，不粘任何业务逻辑
   - 只存对话历史 + 状态标记
   - 不存业务数据（订单、商品等）
   - 不做清洗、不做检索、不跑rerank
   - 不嵌prompt模板、不解析意图

2. 上下文裁剪可预测、可复现
   - 裁剪策略固定、可配置
   - 不随机丢上文
   - Session层只标记"需要裁剪"，不负责处理

3. 干净解耦，只提供接口
   - 只做两件事：存历史、取历史
   - 不调用向量库、不调用LLM、不调用缓存

4. 可回溯、可审计
   - 每轮带唯一ID、时间、轮次
   - 支持清空、过期
"""

# ============================================================
# 基础导入
# ============================================================
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
import uuid


# ============================================================
# 枚举定义
# ============================================================


class SessionType:
    """会话类型（仅用于配置过期时间，不存业务）"""

    CONSULT = "consult"  # 咨询类
    AFTER_SALE = "after_sale"  # 售后类
    GENERAL = "general"  # 通用类


# ============================================================
# 核心类
# ============================================================


class SessionManager:
    """
    会话管理器（只存/取，不思考）

    单例模式：全局共享同一个实例，确保内存中的会话数据在所有步骤间共享。
    """

    _instance: Optional["SessionManager"] = None
    _initialized_flag: bool = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        max_rounds: int = 10,  # 最大保留轮次
        default_expire_minutes: int = 30,  # 默认过期时间
        expire_config: Optional[Dict[str, int]] = None,  # 过期配置
    ):
        """
        初始化

        Args:
            max_rounds: 最大保留轮次（用于触发截断标记）
            default_expire_minutes: 默认过期分钟数
            expire_config: 各类型会话的过期时间配置
        """
        # 防止重复初始化
        if SessionManager._initialized_flag:
            return
        SessionManager._initialized_flag = True

        # 存储：{session_id: SessionContext}
        self._sessions: Dict[str, "SessionContext"] = {}

        # 配置
        self.max_rounds = max_rounds
        self.default_expire_minutes = default_expire_minutes
        self._expire_config = expire_config or {
            SessionType.CONSULT: 3600 * 24,  # 咨询类 24小时
            SessionType.AFTER_SALE: 3600 * 24 * 7,  # 售后类 7天
            SessionType.GENERAL: 3600 * 2,  # 通用类 2小时
        }

    # ========================================================
    # 核心接口：主键判断
    # ========================================================

    def session_exists(self, session_key: str) -> bool:
        """
        检查 session_key 是否存在

        Args:
            session_key: 主键，格式 "{sessionId}:{userId}:{channel}"

        Returns:
            是否存在
        """
        return session_key in self._sessions

    def get_session_by_key(self, session_key: str) -> Optional["SessionContext"]:
        """
        通过 session_key 获取会话

        Args:
            session_key: 主键，格式 "{sessionId}:{userId}:{channel}"

        Returns:
            会话对象，不存在或过期返回None
        """
        session = self._sessions.get(session_key)
        if not session:
            return None
        if session.is_expired():
            return None
        return session

    # ========================================================
    # 核心接口：存
    # ========================================================

    def create_session(
        self,
        user_id: str,
        channel: str = "web",
        session_type: str = SessionType.GENERAL,
        session_key: Optional[str] = None,
    ) -> "SessionContext":
        """
        创建新会话

        Args:
            user_id: 用户ID
            channel: 来源渠道
            session_type: 会话类型（仅用于配置过期时间）

        Returns:
            新建的会话对象
        """
        # 生成唯一会话ID
        if session_key:
            # 使用传入的主键（如 "{sessionId}:{userId}:{channel}"）
            sid = session_key
        else:
            sid = str(uuid.uuid4())

        # 计算过期时间
        expire_minutes = self._expire_config.get(
            session_type, self.default_expire_minutes
        )
        expire_at = (datetime.now() + timedelta(minutes=expire_minutes)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        # 创建会话对象
        session = self._create_session_context(
            session_id=sid,
            user_id=user_id,
            channel=channel,
            expire_at=expire_at,
        )

        # 存到存储，使用 session_key 作为主键
        self._sessions[sid] = session

        return session

    def save_round(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> Tuple[Optional["SessionContext"], Optional["TruncateMarker"]]:
        """
        存一轮对话

        这是唯一写入接口。
        写入后检查是否需要截断，返回截断标记。

        Args:
            session_id: 会话ID
            role: 角色（user/assistant）
            content: 对话内容

        Returns:
            (会话对象, 截断标记 或 None)
            - 如果会话不存在，返回 (None, None)
            - 如果未触发截断，返回 (session, None)
            - 如果触发截断，返回 (session, TruncateMarker)
        """
        # 获取会话
        session = self.get_session(session_id)
        if not session:
            return None, None

        # 当前轮次
        current_round = session.get_current_round()

        # 创建记录
        record = SessionRecord(
            round=current_round + 1,
            request_id=str(uuid.uuid4()),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            role=role,
            content=content,
        )

        # 添加记录
        session.rounds.append(record)
        session.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 检查是否需要截断（固定策略，可预测）
        truncate_marker = self._check_truncate(session)

        return session, truncate_marker

    def update_state(
        self,
        session_id: str,
        state: Dict[str, str],
    ) -> Optional["SessionContext"]:
        """
        更新状态标记

        只存状态标记（如意图、等待输入），
        不存任何业务数据。

        Args:
            session_id: 会话ID
            state: 状态字典（必须是纯字符串）
                   如：{"intent": "query_order", "waiting": "order_id"}

        Returns:
            更新后的会话对象
        """
        session = self.get_session(session_id)
        if not session:
            return None

        # 更新状态（只存字符串）
        session.state = state
        session.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return session

    # ========================================================
    # 核心接口：取
    # ========================================================

    def get_session(self, session_id: str) -> Optional["SessionContext"]:
        """
        获取会话（检查过期）

        Args:
            session_id: 会话ID

        Returns:
            会话对象，不存在或过期返回None
        """
        session = self._sessions.get(session_id)
        if not session:
            return None

        # 检查过期
        if session.is_expired():
            return None

        return session

    def get_rounds(
        self,
        session_id: str,
        keep_rounds: Optional[int] = None,
    ) -> Tuple[Optional[List["SessionRecord"]], Optional["TruncateMarker"]]:
        """
        获取对话轮次

        固定策略：保留最近N轮，不随机丢。

        Args:
            session_id: 会话ID
            keep_rounds: 保留轮次，默认用max_rounds

        Returns:
            (轮次列表, 截断标记 或 None)
        """
        session = self.get_session(session_id)
        if not session:
            return None, None

        # 默认保留全部
        keep = keep_rounds or len(session.rounds)

        # 固定策略：保留最近N轮
        rounds = session.rounds[-keep:] if session.rounds else []

        # 检查是否被截断过
        truncate_marker = None
        if len(session.rounds) > keep:
            truncate_marker = TruncateMarker(
                before_round=len(session.rounds),
                after_round=keep,
                reason="rounds_exceed",
            )

        return rounds, truncate_marker

    def get_state(self, session_id: str) -> Optional[Dict[str, str]]:
        """获取状态标记"""
        session = self.get_session(session_id)
        if not session:
            return None
        return session.state

    def get_user_sessions(self, user_id: str) -> List["SessionContext"]:
        """获取用户的所有活跃会话"""
        return [
            s
            for s in self._sessions.values()
            if s.user_id == user_id and not s.is_expired()
        ]

    # ========================================================
    # Session Key 接口（sessionId:userId:channel 复合主键）
    # ========================================================

    def exists_by_key(self, session_key: str) -> bool:
        """
        检查 session_key 是否存在

        Args:
            session_key: 复合键，格式为 "{sessionId}:{userId}:{channel}"

        Returns:
            是否存在
        """
        return session_key in self._sessions

    def create_by_key(
        self,
        session_key: str,
        user_id: str,
        channel: str,
    ) -> "SessionContext":
        """
        创建新会话（使用复合 session_key）

        Args:
            session_key: 复合键，格式为 "{sessionId}:{userId}:{channel}"
            user_id: 用户ID
            channel: 来源渠道

        Returns:
            新建的会话对象
        """
        # 计算过期时间
        expire_minutes = self.default_expire_minutes
        expire_at = (datetime.now() + timedelta(minutes=expire_minutes)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        # 创建会话对象
        session = self._create_session_context(
            session_id=session_key,
            user_id=user_id,
            channel=channel,
            expire_at=expire_at,
        )

        # 存到存储
        self._sessions[session_key] = session

        return session

    def get_by_key(self, session_key: str) -> Optional["SessionContext"]:
        """
        通过 session_key 获取会话

        Args:
            session_key: 复合键，格式为 "{sessionId}:{userId}:{channel}"

        Returns:
            会话对象，不存在或过期返回None
        """
        session = self._sessions.get(session_key)
        if not session:
            return None

        # 检查过期
        if session.is_expired():
            return None

        return session

    # ========================================================
    # 管理接口
    # ========================================================

    def refresh_session(self, session_id: str) -> Optional["SessionContext"]:
        """刷新会话过期时间"""
        session = self.get_session(session_id)
        if not session:
            return None

        # 直接用默认过期时间
        session.expire_at = (
            datetime.now() + timedelta(minutes=self.default_expire_minutes)
        ).strftime("%Y-%m-%d %H:%M:%S")

        return session

    def clear_session(self, session_id: str) -> bool:
        """清空会话历史（可回溯）"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def clear_user_sessions(self, user_id: str) -> int:
        """清空用户所有会话"""
        count = 0
        to_delete = [sid for sid, s in self._sessions.items() if s.user_id == user_id]
        for sid in to_delete:
            del self._sessions[sid]
            count += 1
        return count

    # ============================================================
    # 内部方法
    # ============================================================

    def _create_session_context(
        self,
        session_id: str,
        user_id: str,
        channel: str,
        expire_at: str,
    ) -> "SessionContext":
        """创建会话对象（工厂方法）"""
        return SessionContext(
            session_id=session_id,
            user_id=user_id,
            channel=channel,
            expire_at=expire_at,
        )

    def _check_truncate(self, session: "SessionContext") -> Optional["TruncateMarker"]:
        """
        检查是否需要截断（固定策略）

        目前只按轮次截断。
        Session层只标记，不负责处理。
        """
        if len(session.rounds) > self.max_rounds:
            return TruncateMarker(
                before_round=len(session.rounds),
                after_round=self.max_rounds,
                reason="rounds_exceed",
            )
        return None

    # ============================================================
    # 文件持久化
    # ============================================================

    def save_to_file(
        self,
        channel: str,
        session_id: str,
        role: str,
        content: str,
        request_id: str = "",
    ):
        """
        保存会话到文件

        Args:
            channel: 渠道
            session_id: 会话ID
            role: 角色 (user/assistant)
            content: 消息内容
            request_id: 请求ID（用于链路追踪）
        """
        from context.session_handler import SessionHandler

        handler = SessionHandler()
        handler.save_session_to_file(channel, session_id, role, content, request_id)


# ============================================================
# 延迟导入（避免循环依赖）
# ============================================================
from .models import SessionContext, SessionRecord, TruncateMarker
