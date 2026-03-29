"""
Pipeline Step 基类

所有Pipeline步骤的基类，定义统一的接口。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
import time
import traceback


class StepType(Enum):
    """步骤类型"""
    AGENT = "agent"       # Agent规划
    TOOLS = "tools"       # 工具执行
    LLM = "llm"         # LLM生成
    OUTPUT = "output"     # 输出合成
    CONTEXT = "context"   # 上下文管理


@dataclass
class StepResult:
    """
    步骤执行结果
    
    Attributes:
        success: 是否成功
        data: 返回数据
        error: 错误信息
        step_name: 步骤名称
        step_type: 步骤类型
        duration: 执行耗时（秒）
        timestamp: 执行时间
        metadata: 额外信息
    """
    success: bool
    data: Any = None
    error: str = ""
    step_name: str = ""
    step_type: str = ""
    duration: float = 0.0
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "step_name": self.step_name,
            "step_type": self.step_type,
            "duration": self.duration,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class Step(ABC):
    """
    Pipeline 步骤基类
    
    所有Pipeline步骤必须继承此类并实现 execute 方法。
    
    使用示例：
        class MyStep(Step):
            def __init__(self):
                super().__init__("my_step", StepType.AGENT)
            
            def _do_execute(self, context: dict) -> StepResult:
                # 业务逻辑
                return StepResult(success=True, data={"result": "ok"})
    """
    
    def __init__(
        self,
        name: str,
        step_type: StepType,
        optional: bool = False,
        timeout: int = 30,
    ):
        """
        初始化步骤
        
        Args:
            name: 步骤名称（唯一标识）
            step_type: 步骤类型
            optional: 是否可选（失败时是否中断Pipeline）
            timeout: 超时秒数
        """
        self.name = name
        self.step_type = step_type
        self.optional = optional
        self.timeout = timeout
    
    def execute(self, context: dict) -> StepResult:
        """
        执行步骤（模板方法）
        
        包含：计时、异常捕获、trace记录
        """
        start_time = time.time()
        
        try:
            result = self._do_execute(context)
            result.step_name = self.name
            result.step_type = self.step_type.value
            result.duration = time.time() - start_time
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            return StepResult(
                success=False,
                error=f"{type(e).__name__}: {str(e)}",
                step_name=self.name,
                step_type=self.step_type.value,
                duration=duration,
            )
    
    @abstractmethod
    def _do_execute(self, context: dict) -> StepResult:
        """
        业务逻辑（子类实现）
        
        Args:
            context: Pipeline上下文
            
        Returns:
            StepResult: 执行结果
        """
        pass

    def __repr__(self):
        return f"Step({self.name}, type={self.step_type.value})"
