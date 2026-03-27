"""
Prompt 模板模块

提供 Prompt 模板的加载、管理和渲染功能。

设计思想：
- 模板与逻辑分离：模板定义在 templates.json，代码只负责渲染
- 变量替换：支持 {{variable}} 格式的变量替换
- 分类管理：不同场景（对话、工具、回复）使用不同模板

文件结构：
- manager.py: PromptManager 负责加载和管理模板
- templates.json: 模板文件（用户可编辑）
"""

from .manager import PromptManager, get_prompt_manager

__all__ = [
    "PromptManager",
    "get_prompt_manager",
]
