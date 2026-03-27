"""
StructuredLogger 结构化日志
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any
import json


class StructuredLogger:
    """
    结构化日志
    
    输出JSON格式日志，便于收集和分析。
    """
    
    def __init__(self, name: str = "app"):
        self.name = name
    
    def _format(self, level: str, msg: str, extra: Optional[Dict] = None) -> str:
        log = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "name": self.name,
            "message": msg,
        }
        if extra:
            log.update(extra)
        return json.dumps(log, ensure_ascii=False)
    
    def info(self, msg: str, **extra):
        print(self._format("INFO", msg, extra))
    
    def error(self, msg: str, **extra):
        print(self._format("ERROR", msg, extra))
    
    def warning(self, msg: str, **extra):
        print(self._format("WARNING", msg, extra))
    
    def debug(self, msg: str, **extra):
        print(self._format("DEBUG", msg, extra))


_logger: Optional[StructuredLogger] = None


def get_logger(name: str = "app") -> StructuredLogger:
    global _logger
    if _logger is None:
        _logger = StructuredLogger(name)
    return _logger
