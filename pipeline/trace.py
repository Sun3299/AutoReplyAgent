"""
链路追踪模块

记录每个步骤的执行情况，支持分布式trace。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum
import json


class TraceStatus(Enum):
    """执行状态"""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    FALLBACK = "fallback"


@dataclass
class Span:
    """
    链路中的一个节点（一个步骤的执行记录）
    
    Attributes:
        trace_id: 链路ID
        span_id: 节点ID
        name: 步骤名称
        status: 执行状态
        start_time: 开始时间
        end_time: 结束时间
        duration: 执行时长（秒）
        duration_ms: 执行时长（毫秒）
        parent_id: 父节点ID（用于嵌套）
        metadata: 额外数据
        error: 错误信息
    """
    trace_id: str
    span_id: str
    name: str
    status: TraceStatus = TraceStatus.SUCCESS
    start_time: str = ""
    end_time: str = ""
    duration: float = 0.0
    duration_ms: float = 0.0
    parent_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    
    def __post_init__(self):
        if not self.start_time:
            self.start_time = datetime.now().isoformat()
    
    def finish(self, status: TraceStatus = TraceStatus.SUCCESS, error: str = ""):
        self.end_time = datetime.now().isoformat()
        self.status = status
        self.error = error
        start_dt = datetime.fromisoformat(self.start_time)
        end_dt = datetime.fromisoformat(self.end_time)
        self.duration = (end_dt - start_dt).total_seconds()
        self.duration_ms = self.duration * 1000
    
    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "name": self.name,
            "status": self.status.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "duration_ms": self.duration_ms,
            "parent_id": self.parent_id,
            "metadata": self.metadata,
            "error": self.error,
        }


@dataclass
class Trace:
    """
    完整链路记录
    
    Attributes:
        trace_id: 链路ID
        user_id: 用户ID
        request: 用户请求
        response: 系统回复
        status: 最终状态
        total_duration: 总耗时
        spans: 所有节点列表
        created_at: 创建时间
    """
    trace_id: str
    user_id: str = ""
    request: str = ""
    response: str = ""
    status: TraceStatus = TraceStatus.SUCCESS
    total_duration: float = 0.0
    spans: List[Span] = field(default_factory=list)
    created_at: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
    
    def add_span(self, span: Span):
        """添加节点"""
        self.spans.append(span)
    
    def finish(self, status: TraceStatus = TraceStatus.SUCCESS):
        """完成链路"""
        self.status = status
        self.total_duration = sum(s.duration for s in self.spans)
    
    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "user_id": self.user_id,
            "request": self.request,
            "response": self.response,
            "status": self.status.value,
            "total_duration": self.total_duration,
            "spans": [s.to_dict() for s in self.spans],
            "created_at": self.created_at,
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class TraceManager:
    """
    链路管理器
    
    管理链路的创建、存储、查询。
    
    使用示例：
        manager = TraceManager()
        
        # 开始链路
        trace = manager.start_trace("user123", "查订单")
        
        # 添加节点
        span = trace.add_span("agent", "Agent规划")
        # ... 执行步骤 ...
        span.finish()
        
        # 结束链路
        trace.finish()
        
        # 保存
        manager.save(trace)
    """
    
    def __init__(self, storage: Optional[Any] = None):
        """
        Args:
            storage: 存储后端（内存/Redis/DB）
        """
        self.storage = storage or {}  # 内存存储
        self._current_trace: Optional[Trace] = None
    
    def start_trace(
        self,
        user_id: str,
        request: str,
        trace_id: Optional[str] = None,
    ) -> Trace:
        """开始一条链路"""
        import uuid
        
        trace = Trace(
            trace_id=trace_id or str(uuid.uuid4()),
            user_id=user_id,
            request=request,
        )
        self._current_trace = trace
        return trace
    
    def current_trace(self) -> Optional[Trace]:
        """获取当前链路"""
        return self._current_trace
    
    def add_span(
        self,
        name: str,
        parent_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Span:
        """在当前链路中添加节点"""
        import uuid
        
        trace = self._current_trace
        if not trace:
            raise RuntimeError("No active trace. Call start_trace() first.")
        
        span = Span(
            trace_id=trace.trace_id,
            span_id=str(uuid.uuid4()),
            name=name,
            parent_id=parent_id,
            metadata=metadata or {},
        )
        trace.add_span(span)
        return span
    
    def finish_span(
        self,
        span_id: str,
        status: TraceStatus = TraceStatus.SUCCESS,
        error: str = "",
    ):
        """标记节点完成"""
        trace = self._current_trace
        if not trace:
            return
        
        for span in trace.spans:
            if span.span_id == span_id:
                span.finish(status=status, error=error)
                break
    
    def finish_trace(
        self,
        status: TraceStatus = TraceStatus.SUCCESS,
        response: str = "",
    ) -> Trace:
        """结束链路"""
        trace = self._current_trace
        if trace:
            trace.response = response
            trace.finish(status=status)
            self.save(trace)
            self._current_trace = None
        return trace
    
    def save(self, trace: Trace):
        """保存链路"""
        self.storage[trace.trace_id] = trace
    
    def get(self, trace_id: str) -> Optional[Trace]:
        """获取链路"""
        return self.storage.get(trace_id)
    
    def list_by_user(self, user_id: str, limit: int = 100) -> List[Trace]:
        """查询用户的链路"""
        return [
            t for t in self.storage.values()
            if t.user_id == user_id
        ][:limit]
    
    def metrics(self) -> dict:
        """聚合指标"""
        if not self.storage:
            return {"total": 0}
        
        total = len(self.storage)
        success = sum(1 for t in self.storage.values() if t.status == TraceStatus.SUCCESS)
        errors = total - success
        avg_duration = (
            sum(t.total_duration for t in self.storage.values()) / total if total > 0 else 0
        )
        
        return {
            "total": total,
            "success": success,
            "error": errors,
            "avg_duration": avg_duration,
        }
