"""
Output Filters

敏感词过滤和长度校验模块。
"""

from typing import List, Optional, Tuple
import os


class SensitiveWordFilter:
    """
    敏感词过滤器
    
    从文件加载敏感词列表，对文本进行敏感词检测和过滤。
    
    Attributes:
        _words: 敏感词列表（类变量，跨实例共享）
        _loaded: 是否已加载
    """
    
    _words: Optional[List[str]] = None
    _loaded: bool = False
    
    def __init__(self, words_file: Optional[str] = None):
        """
        初始化过滤器
        
        Args:
            words_file: 敏感词文件路径，默认使用 config/sensitive_words.txt
        """
        self._words_file = words_file
        if not SensitiveWordFilter._loaded:
            self._load_words()
    
    def _load_words(self) -> None:
        """加载敏感词列表（仅加载一次）"""
        if SensitiveWordFilter._loaded:
            return
        
        if SensitiveWordFilter._words is None:
            SensitiveWordFilter._words = []
        
        if self._words_file is None:
            # 默认路径：项目根目录/config/sensitive_words.txt
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self._words_file = os.path.join(base_dir, "config", "sensitive_words.txt")
        
        if os.path.exists(self._words_file):
            with open(self._words_file, "r", encoding="utf-8") as f:
                SensitiveWordFilter._words = [
                    line.strip() for line in f if line.strip()
                ]
        
        SensitiveWordFilter._loaded = True
    
    def filter(self, text: str) -> Tuple[str, bool]:
        """
        过滤敏感词
        
        Args:
            text: 输入文本
            
        Returns:
            Tuple[str, bool]: (过滤后的文本, 是否被修改)
        """
        if not text or not SensitiveWordFilter._words:
            return text, False
        
        modified = False
        result = text
        
        for word in SensitiveWordFilter._words:
            if word in result:
                result = result.replace(word, "*" * len(word))
                modified = True
        
        return result, modified
    
    @classmethod
    def reload(cls) -> None:
        """重新加载敏感词列表"""
        cls._loaded = False
        cls._words = None


class LengthValidator:
    """
    长度验证器
    
    验证文本长度是否在指定范围内。
    
    Attributes:
        min_length: 最小长度
        max_length: 最大长度
    """
    
    def __init__(self, min_length: int = 1, max_length: int = 2000):
        """
        初始化验证器
        
        Args:
            min_length: 最小长度，默认 1
            max_length: 最大长度，默认 2000
        """
        self.min_length = min_length
        self.max_length = max_length
    
    def validate(self, text: str) -> Tuple[bool, str]:
        """
        验证文本长度
        
        Args:
            text: 输入文本
            
        Returns:
            Tuple[bool, str]: (是否有效, 错误消息)
        """
        if not text:
            return False, "文本不能为空"
        
        length = len(text)
        
        if length < self.min_length:
            return False, f"文本长度不能少于 {self.min_length} 个字符"
        
        if length > self.max_length:
            return False, f"文本长度不能超过 {self.max_length} 个字符"
        
        return True, ""
