"""
Prompt 管理器

负责 Prompt 模板的加载、管理和渲染。

核心功能：
1. 加载模板：从 JSON 文件/字符串加载模板
2. 变量替换：将 {{variable}} 替换为实际值
3. 模板缓存：避免重复解析
4. 模板分类：区分不同类型模板
"""

import json
from pathlib import Path
import re
from typing import Any, Dict, Optional, List
from dataclasses import dataclass, field


@dataclass
class PromptTemplate:
    """
    Prompt 模板
    
    Attributes:
        name: 模板名称
        content: 模板内容
        variables: 模板中的变量列表
        description: 模板描述
    """
    name: str                              # 模板名称
    content: str                            # 模板内容
    variables: List[str] = field(default_factory=list)  # 变量列表
    description: str = ""                  # 描述


class PromptManager:
    """
    Prompt 管理器
    
    统一管理所有 Prompt 模板，提供加载和渲染功能。
    
    加载优先级：
    1. prompt/templates.json（默认模板）
    
    Attributes:
        _templates: 已加载的模板字典
        _cache: 渲染结果缓存
    
    使用示例：
        manager = PromptManager()
        
        # 加载模板（自动从 templates.json 加载）
        result = manager.render("system", name="小Auto")
        
        # 手动加载模板
        manager.load_template("greeting", "你好，{{name}}！")
        result = manager.render("greeting", name="小明")
    """
    
    def __init__(self):
        """初始化 Prompt 管理器"""
        self._templates: Dict[str, PromptTemplate] = {}  # 模板存储
        self._cache: Dict[str, str] = {}  # 渲染缓存
    
    def load_templates_from_json(self, json_path: str = None):
        """
        从 JSON 文件加载模板
        
        Args:
            json_path: JSON 文件路径，默认为 prompt/templates.json
        """
        if json_path is None:
            json_path = Path(__file__).parent / "templates.json"
        
        json_file = Path(json_path)
        if not json_file.exists():
            print(f"警告：模板文件不存在: {json_path}")
            return
        
        with open(json_file, 'r', encoding='utf-8') as f:
            templates = json.load(f)
        
        for name, content in templates.items():
            if isinstance(content, str):
                self.load_template(name, content)
            elif isinstance(content, dict):
                self.load_template(
                    name, 
                    content.get("content", ""),
                    content.get("description", "")
                )
    
    def load_template(
        self,
        name: str,
        content: str,
        description: str = ""
    ) -> PromptTemplate:
        """
        加载模板
        
        Args:
            name: 模板名称（唯一标识）
            content: 模板内容，支持 {{variable}} 格式
            description: 模板描述
            
        Returns:
            PromptTemplate 对象
        """
        variables = self._extract_variables(content)
        
        template = PromptTemplate(
            name=name,
            content=content,
            variables=variables,
            description=description
        )
        
        self._templates[name] = template
        return template
    
    def load_templates(self, templates: Dict[str, str]):
        """
        批量加载模板
        
        Args:
            templates: 模板字典 {"name": "content"}
        """
        for name, content in templates.items():
            self.load_template(name, content)
    
    def get_template(self, name: str) -> Optional[PromptTemplate]:
        """获取模板"""
        return self._templates.get(name)
    
    def list_templates(self) -> List[str]:
        """列出所有已加载的模板名称"""
        return list(self._templates.keys())
    
    def render(self, **kwargs) -> str:
        """
        渲染模板
        
        Args:
            **kwargs: 必须包含 _name（模板名），以及其他变量
            
        Returns:
            渲染后的字符串
        """
        name = kwargs.get("_name")
        if not name:
            raise ValueError("缺少模板名称参数 _name")
        
        template = self._templates.get(name)
        if not template:
            raise KeyError(f"模板不存在: {name}")
        
        # 检查必需变量
        missing = set(template.variables) - set(kwargs.keys())
        if missing:
            raise ValueError(f"缺少变量: {missing}")
        
        # 替换变量
        result = template.content
        for var_name, var_value in kwargs.items():
            placeholder = f"{{{{{var_name}}}}}"
            result = result.replace(placeholder, str(var_value))
        
        return result
    
    def render_batch(self, **kwargs) -> List[str]:
        """
        批量渲染模板
        
        Args:
            **kwargs: 必须包含 _name 和 params_list
            
        Returns:
            渲染结果列表
        """
        name = kwargs.get("_name")
        params_list = kwargs.get("params_list", [])
        return [self.render(_name=name, **params) for params in params_list]
    
    def _extract_variables(self, content: str) -> List[str]:
        """提取模板中的变量"""
        pattern = r'\{\{(\w+)\}\}'
        matches = re.findall(pattern, content)
        seen = set()
        result = []
        for var in matches:
            if var not in seen:
                seen.add(var)
                result.append(var)
        return result
    
    def clear_cache(self):
        """清空渲染缓存"""
        self._cache.clear()
    
    def clear_templates(self):
        """清空所有模板"""
        self._templates.clear()
        self.clear_cache()


# 全局单例
_manager: Optional[PromptManager] = None


def get_prompt_manager() -> PromptManager:
    """
    获取全局 Prompt 管理器实例
    
    自动加载 templates.json
    
    Returns:
        PromptManager 单例
    """
    global _manager
    if _manager is None:
        _manager = PromptManager()
        # 加载默认模板
        _manager.load_templates_from_json()
    return _manager
