"""
Pipeline 数据模型

PipelineStepInput, PipelineStepOutput, StepMetrics 等步骤间数据结构。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class StepMetrics:
    """步骤执行指标"""
    step_name: str
    duration_ms: float
    success: bool


@dataclass
class PipelineStepInput:
    """Pipeline步骤输入"""
    step_name: str
    input_data: Dict[str, Any]
    context: Dict[str, Any]


@dataclass
class PipelineStepOutput:
    """Pipeline步骤输出"""
    step_name: str
    output_data: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
