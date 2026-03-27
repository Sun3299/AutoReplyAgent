"""
Output 模块测试
"""

import pytest
import sys
sys.path.insert(0, '..')


class TestOutputContext:
    """OutputContext 测试"""
    
    def test_context_创建(self):
        """Context 能正常创建"""
        from output import OutputContext
        
        ctx = OutputContext(
            rag_results=["结果1"],
            intent="test"
        )
        assert ctx.rag_results == ["结果1"]
        assert ctx.intent == "test"


class TestOutputSynthesizer:
    """OutputSynthesizer 测试"""
    
    def test_synthesizer_创建(self):
        """合成器能正常创建"""
        from output import OutputSynthesizer
        
        synth = OutputSynthesizer()
        assert synth is not None
    
    def test_synthesize_工具结果(self):
        """工具结果合成"""
        from output import OutputSynthesizer, OutputContext
        
        synth = OutputSynthesizer()
        ctx = OutputContext(
            tool_results=[
                {"success": True, "data": {"order_id": "12345"}}
            ]
        )
        
        result = synth.synthesize(ctx)
        
        assert result.source == "tool"
        assert "12345" in result.content
    
    def test_synthesize_RAG结果(self):
        """RAG 结果合成"""
        from output import OutputSynthesizer, OutputContext
        
        synth = OutputSynthesizer()
        ctx = OutputContext(
            rag_results=["退货政策是7天内"]
        )
        
        result = synth.synthesize(ctx)
        
        assert result.source == "rag"
        assert "退货政策" in result.content
    
    def test_synthesize_LLM输出(self):
        """LLM 输出合成"""
        from output import OutputSynthesizer, OutputContext
        
        synth = OutputSynthesizer()
        ctx = OutputContext(
            llm_output="这是 LLM 的回复"
        )
        
        result = synth.synthesize(ctx)
        
        assert result.source == "llm"
        assert "LLM" in result.content
    
    def test_synthesize_工具结果优先(self):
        """工具结果优先于 RAG"""
        from output import OutputSynthesizer, OutputContext
        
        synth = OutputSynthesizer()
        ctx = OutputContext(
            tool_results=[{"success": True, "data": "tool_result"}],
            rag_results=["rag_result"],
            llm_output="llm_output"
        )
        
        result = synth.synthesize(ctx)
        
        assert result.source == "tool"
    
    def test_synthesize_空结果(self):
        """空结果返回默认回复"""
        from output import OutputSynthesizer, OutputContext
        
        synth = OutputSynthesizer()
        ctx = OutputContext()
        
        result = synth.synthesize(ctx)
        
        assert result.source == "fallback"


class TestReplyStrategy:
    """ReplyStrategy 测试"""
    
    def test_direct_strategy(self):
        """直接回复策略"""
        from output import DirectStrategy, OutputContext
        
        strategy = DirectStrategy()
        ctx = OutputContext(llm_output="直接回复")
        
        result = strategy.synthesize(ctx)
        
        assert result.content == "直接回复"
        assert result.source == "direct"
    
    def test_rag_first_strategy(self):
        """RAG 优先策略"""
        from output import RagFirstStrategy, OutputContext
        
        strategy = RagFirstStrategy()
        ctx = OutputContext(
            rag_results=["知识1", "知识2"]
        )
        
        result = strategy.synthesize(ctx)
        
        assert result.source == "rag_first"
        assert "知识1" in result.content
    
    def test_tool_first_strategy(self):
        """工具优先策略"""
        from output import ToolFirstStrategy, OutputContext
        
        strategy = ToolFirstStrategy()
        ctx = OutputContext(
            tool_results=[
                {"success": True, "data": {"status": "已发货"}}
            ]
        )
        
        result = strategy.synthesize(ctx)
        
        assert result.source == "tool"
        assert "已发货" in result.content
    
    def test_hybrid_strategy(self):
        """混合策略"""
        from output import HybridStrategy, OutputContext
        
        strategy = HybridStrategy()
        ctx = OutputContext(
            rag_results=["知识参考"],
            tool_results=[{"success": True, "data": "查询结果"}],
            llm_output="智能补充"
        )
        
        result = strategy.synthesize(ctx)
        
        assert "知识参考" in result.content
        assert "查询结果" in result.content
        assert "智能补充" in result.content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
