"""
LLM 模块测试
"""

import pytest
import sys
sys.path.insert(0, '..')


class TestLLMBase:
    """LLM 基础类测试"""
    
    def test_message_创建(self):
        """Message 能正常创建"""
        from llm.base import Message, MessageRole
        
        msg = Message(role=MessageRole.USER, content="你好")
        assert msg.role == MessageRole.USER
        assert msg.content == "你好"
    
    def test_message_role_值(self):
        """MessageRole 枚举值正确"""
        from llm.base import MessageRole
        
        assert MessageRole.USER.value == "user"
        assert MessageRole.ASSISTANT.value == "assistant"
        assert MessageRole.SYSTEM.value == "system"
    
    def test_llm_config_默认值(self):
        """LLMConfig 默认值正确"""
        from llm.base import LLMConfig
        
        config = LLMConfig()
        assert config.model == "gpt-3.5-turbo"
        assert config.temperature == 0.7
        assert config.max_tokens == 2000
    
    def test_llm_response_创建(self):
        """LLMResponse 能正常创建"""
        from llm.base import LLMResponse
        
        resp = LLMResponse(
            content="测试回复",
            usage={"prompt_tokens": 10},
            model="test-model"
        )
        assert resp.content == "测试回复"
        assert resp.usage["prompt_tokens"] == 10


class TestLLMFactory:
    """LLM 工厂测试"""
    
    def test_factory_创建(self):
        """工厂能正常创建"""
        from llm.factory import LLMFactory
        
        factory = LLMFactory()
        assert factory is not None
    
    def test_factory_注册(self):
        """Provider 注册功能"""
        from llm.factory import LLMFactory
        from llm.base import BaseLLMProvider
        
        class TestProvider(BaseLLMProvider):
            @property
            def name(self):
                return "test"
            
            def chat(self, messages, config=None):
                pass
            
            async def achat(self, messages, config=None):
                pass
            
            def chat_stream(self, messages, config=None):
                yield ""
        
        factory = LLMFactory()
        factory.register("test", TestProvider)
        
        assert "test" in factory.list_providers()
    
    def test_factory_创建实例(self):
        """Provider 实例创建"""
        from llm.factory import LLMFactory
        from llm.base import BaseLLMProvider
        
        class TestProvider(BaseLLMProvider):
            @property
            def name(self):
                return "test"
            
            def chat(self, messages, config=None):
                pass
            
            async def achat(self, messages, config=None):
                pass
            
            def chat_stream(self, messages, config=None):
                yield ""
        
        factory = LLMFactory()
        factory.register("test", TestProvider)
        
        instance = factory.create("test")
        assert instance.name == "test"
    
    def test_factory_未注册报错(self):
        """未注册的 Provider 抛出异常"""
        from llm.factory import LLMFactory
        
        factory = LLMFactory()
        
        with pytest.raises(ValueError, match="未注册"):
            factory.create("not_exist")


class TestMockProvider:
    """Mock Provider 测试"""
    
    def test_mock_provider_创建(self):
        """Mock Provider 能正常创建"""
        from llm.providers import MockLLMProvider
        
        provider = MockLLMProvider("测试回复")
        assert provider.name == "mock"
    
    def test_mock_provider_chat(self):
        """Mock Provider chat 返回预设内容"""
        from llm.providers import MockLLMProvider
        from llm.base import Message, MessageRole
        
        provider = MockLLMProvider("测试回复")
        messages = [Message(role=MessageRole.USER, content="你好")]
        
        response = provider.chat(messages)
        
        assert response.content == "测试回复"
        assert response.model == "mock"


class TestMiniMaxProvider:
    """MiniMax Provider 测试"""
    
    def test_minimax_provider_创建(self):
        """MiniMax Provider 能正常创建"""
        from llm.providers import MiniMaxProvider
        
        provider = MiniMaxProvider(api_key="test-key")
        assert provider.name == "minimax"
        assert provider.api_key == "test-key"
    
    def test_minimax_provider_配置(self):
        """MiniMax Provider 配置正确"""
        from llm.providers import MiniMaxProvider
        
        provider = MiniMaxProvider(
            api_key="test-key",
            model="test-model",
            base_url="https://test.com"
        )
        
        config = provider.default_config
        assert config.model == "test-model"
        assert config.api_key == "test-key"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
