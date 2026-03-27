"""
Prompt 模块测试
"""

import pytest
import sys
sys.path.insert(0, '..')


class TestPromptManager:
    """Prompt 管理器测试"""
    
    def test_manager_创建(self):
        """管理器能正常创建"""
        from prompt import PromptManager
        manager = PromptManager()
        assert manager is not None
    
    def test_manager_加载模板(self):
        """加载模板功能"""
        from prompt import PromptManager
        manager = PromptManager()
        
        manager.load_template("greeting", "你好，{{name}}！")
        
        template = manager.get_template("greeting")
        assert template is not None
        assert template.name == "greeting"
        assert template.content == "你好，{{name}}！"
    
    def test_manager_提取变量(self):
        """变量提取功能"""
        from prompt import PromptManager
        manager = PromptManager()
        
        manager.load_template("test", "{{name}}说{{message}}")
        
        template = manager.get_template("test")
        assert "name" in template.variables
        assert "message" in template.variables
    
    def test_manager_渲染单个变量(self):
        """单个变量渲染"""
        from prompt import PromptManager
        manager = PromptManager()
        
        manager.load_template("greeting", "你好，{{name}}！")
        result = manager.render(_name="greeting", name="小明")
        
        assert result == "你好，小明！"
    
    def test_manager_渲染多个变量(self):
        """多个变量渲染"""
        from prompt import PromptManager
        manager = PromptManager()
        
        manager.load_template("test", "{{greeting}}，{{name}}！")
        result = manager.render(_name="test", greeting="你好", name="小明")
        
        assert result == "你好，小明！"
    
    def test_manager_缺少变量(self):
        """缺少变量时抛出异常"""
        from prompt import PromptManager
        manager = PromptManager()
        
        manager.load_template("test", "{{name}}说{{message}}")
        
        with pytest.raises(ValueError, match="缺少变量"):
            manager.render(_name="test", name="小明")  # 缺少 message
    
    def test_manager_不存在模板(self):
        """不存在的模板抛出异常"""
        from prompt import PromptManager
        manager = PromptManager()
        
        with pytest.raises((KeyError, ValueError)):
            manager.render(_name="not_exist", name="小明")
    
    def test_manager_批量渲染(self):
        """批量渲染"""
        from prompt import PromptManager
        manager = PromptManager()
        
        manager.load_template("greeting", "你好，{{name}}！")
        results = manager.render_batch(_name="greeting", params_list=[
            {"name": "小明"},
            {"name": "小红"}
        ])
        
        assert len(results) == 2
        assert results[0] == "你好，小明！"
        assert results[1] == "你好，小红！"
    
    def test_manager_批量加载(self):
        """批量加载模板"""
        from prompt import PromptManager
        manager = PromptManager()
        
        templates = {
            "t1": "{{a}}",
            "t2": "{{b}}"
        }
        manager.load_templates(templates)
        
        assert manager.get_template("t1") is not None
        assert manager.get_template("t2") is not None


class TestPromptTemplates:
    """内置模板测试"""
    
    def test_内置模板存在(self):
        """内置模板都能获取"""
        from prompt import (
            SYSTEM_PROMPT,
            USER_PROMPT,
            TOOL_CALL_PROMPT,
            RAG_CONTEXT_PROMPT,
        )
        
        assert SYSTEM_PROMPT is not None
        assert USER_PROMPT is not None
        assert TOOL_CALL_PROMPT is not None
        assert RAG_CONTEXT_PROMPT is not None
    
    def test_全局管理器加载内置模板(self):
        """全局管理器加载了内置模板"""
        from prompt import get_prompt_manager
        
        manager = get_prompt_manager()
        
        assert manager.get_template("system") is not None
        assert manager.get_template("user") is not None
        assert manager.get_template("tool_call") is not None
        assert manager.get_template("rag_context") is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
