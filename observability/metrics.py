"""
MetricsCollector 指标收集器

收集和暴露Prometheus格式指标。
"""

from dataclasses import dataclass, field
from typing import Dict, List
from datetime import datetime
import json


@dataclass
class Metric:
    """指标"""
    name: str
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class MetricsCollector:
    """
    指标收集器
    
    收集请求量、延迟、错误率等指标。
    
    输出Prometheus格式。
    """
    
    def __init__(self):
        self._metrics: Dict[str, List[Metric]] = {}
    
    def record(self, name: str, value: float, labels: Dict[str, str] = None):
        """记录指标"""
        metric = Metric(name=name, value=value, labels=labels or {})
        if name not in self._metrics:
            self._metrics[name] = []
        self._metrics[name].append(metric)
    
    def counter(self, name: str, labels: Dict[str, str] = None):
        """计数器+1"""
        self.record(name, 1, labels)
    
    def gauge(self, name: str, value: float, labels: Dict[str, str] = None):
        """仪表值"""
        self.record(name, value, labels)
    
    def histogram(self, name: str, value: float, labels: Dict[str, str] = None):
        """直方图"""
        self.record(name, value, labels)
    
    def export(self) -> str:
        """导出Prometheus格式"""
        lines = []
        for name, metrics in self._metrics.items():
            for m in metrics:
                labels = ",".join(f'{k}="{v}"' for k, v in m.labels.items())
                label_str = f"{{{labels}}}" if labels else ""
                lines.append(f"{name}{label_str} {m.value}")
        return "\n".join(lines)
    
    def summary(self) -> Dict:
        """聚合汇总"""
        return {
            "total_requests": sum(
                m.value for ms in self._metrics.values()
                for m in ms
            ),
            "metrics_count": len(self._metrics),
        }


_collector: MetricsCollector = None


def get_metrics() -> MetricsCollector:
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector
