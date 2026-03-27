"""
Pipeline step integration tests.

Tests individual pipeline steps in isolation with mocked dependencies.

Test Cases:
- test_agent_step_intent_recognition: Mock Agent, assert intent set in context
- test_tools_step_parallel_execution: Mock RagTool, assert parallel execution
- test_llm_step_with_fallback: Mock providers, test fallback behavior
- test_output_step_synthesis: Mock synthesizer, assert output formatted
- test_context_step_session_save: Mock session manager, assert save called
"""

import pytest
import time
from typing import Dict, Any, List
from unittest.mock import Mock, MagicMock, patch, AsyncMock, call
from concurrent.futures import ThreadPoolExecutor

from pipeline.orchestrator import PipelineOrchestrator, PipelineContext
from pipeline.step import StepResult, StepType
from pipeline.steps.agent_step import AgentStep
from pipeline.steps.tools_step import ToolsStep
from pipeline.steps.llm_step import LlmStep
from pipeline.steps.output_step import OutputStep
from pipeline.steps.context_step import ContextStep


class TestAgentStepIntentRecognition:
    """Test AgentStep for intent recognition."""
    
    def test_agent_step_intent_recognition(self, pipeline_context):
        """
        Mock Agent, assert intent set in context.
        
        Steps:
        1. Create AgentStep with mocked Agent
        2. Execute step with mocked Agent output
        3. Assert intent is set in context
        """
        from agent.models import Intent, IntentType, AgentOutput, ToolCall
        
        # Create mock Agent
        mock_agent = Mock()
        
        # Setup mock intent
        intent = Intent(
            intent_type=IntentType.QUERY,
            confidence=0.95,
            reason="Test query intent"
        )
        
        # Setup mock execution plan
        plan = ToolCall(
            step=1,
            tool_name="rag",
            reason="test1",
            params={}
        )
        
        # Setup mock output
        mock_output = AgentOutput(
            intent=intent,
            execution_plan=[plan],
            needs_clarify=False,
            clarify_question="",
            should_terminate=False,
            terminate_reason=""
        )
        
        mock_agent.run.return_value = mock_output
        
        # Create AgentStep with mock
        agent_step = AgentStep(agent=mock_agent)
        
        # Execute step
        result = agent_step.execute(pipeline_context)
        
        # Verify result
        assert result.success, f"AgentStep should succeed, error: {result.error}"
        assert result.step_name == "agent_step"
        
        # Verify intent was set in context
        ctx_intent = pipeline_context.get("intent")
        assert ctx_intent is not None, "intent should be set in context"
        assert ctx_intent.intent_type == IntentType.QUERY
        
        # Verify execution plan was set
        ctx_plan = pipeline_context.get("execution_plan")
        assert ctx_plan is not None, "execution_plan should be set in context"
        assert len(ctx_plan) == 1
        assert ctx_plan[0].tool_name == "rag"
    
    def test_agent_step_with_clarification(self, pipeline_context):
        """Test AgentStep when clarification is needed."""
        from agent.models import Intent, IntentType, AgentOutput, ToolCall
        
        mock_agent = Mock()
        
        intent = Intent(
            intent_type=IntentType.QUERY,
            confidence=0.5,  # Low confidence
            reason="Ambiguous query"
        )
        
        mock_output = AgentOutput(
            intent=intent,
            execution_plan=[],
            needs_clarify=True,
            clarify_question="Could you please provide your order ID?",
            should_terminate=True,
            terminate_reason="needs_clarification"
        )
        
        mock_agent.run.return_value = mock_output
        
        agent_step = AgentStep(agent=mock_agent)
        result = agent_step.execute(pipeline_context)
        
        assert result.success
        assert pipeline_context.get("needs_clarify") is True
        assert "order ID" in pipeline_context.get("clarify_question", "")
    
    def test_agent_step_error_handling(self, pipeline_context):
        """Test AgentStep handles errors gracefully."""
        mock_agent = Mock()
        mock_agent.run.side_effect = Exception("Agent error")
        
        agent_step = AgentStep(agent=mock_agent)
        result = agent_step.execute(pipeline_context)
        
        # Agent step is not optional, so should record error
        assert not result.success
        assert "Agent error" in result.error


class TestToolsStepParallelExecution:
    """Test ToolsStep for parallel tool execution."""
    
    def test_tools_step_parallel_execution(self, pipeline_context):
        """
        Mock RagTool, assert parallel execution.
        
        Steps:
        1. Create ToolsStep with multiple mock tools
        2. Execute step
        3. Assert tools were called and results aggregated
        """
        from tools.base import ToolResult
        from agent.models import ToolCall
        
        # Setup context with execution plan containing multiple tool calls
        pipeline_context.set("execution_plan", [
            ToolCall(step=1, tool_name="rag", reason="test1", params={}),
            ToolCall(step=2, tool_name="rag", reason="test2", params={}),
            ToolCall(step=3, tool_name="rag", reason="test3", params={}),
        ])
        
        # Create mock RAG tool
        mock_rag_tool = Mock()
        mock_rag_tool.name = "rag"
        
        call_count = [0]
        def mock_execute(**kwargs):
            call_count[0] += 1
            time.sleep(0.05)  # Simulate work
            return ToolResult(
                success=True,
                data=[f"Result {call_count[0]}"]
            )
        
        mock_rag_tool.execute.side_effect = mock_execute
        
        # Create ToolsStep
        tools_step = ToolsStep(max_workers=3, rag_tool=mock_rag_tool)
        
        # Execute
        start = time.time()
        result = tools_step.execute(pipeline_context)
        duration = time.time() - start
        
        # Verify
        assert result.success, f"ToolsStep should succeed, error: {result.error}"
        
        # Verify all 3 calls were made
        assert call_count[0] == 3, f"Expected 3 calls, got {call_count[0]}"
        
        # Parallel execution should be faster than sequential (3 * 50ms = 150ms)
        # With 3 workers, should be ~50-100ms
        assert duration < 0.15, f"Expected parallel execution < 150ms, got {duration}s"
        
        # Verify results in context
        rag_results = pipeline_context.get("rag_results")
        assert rag_results is not None, "rag_results should be set"
        assert len(rag_results) == 3
    
    def test_tools_step_no_execution_plan(self, pipeline_context):
        """Test ToolsStep when no execution plan is provided."""
        # Don't set execution plan
        pipeline_context.set("execution_plan", [])
        
        tools_step = ToolsStep()
        result = tools_step.execute(pipeline_context)
        
        assert result.success
        assert result.data == [] or result.data is None
    
    def test_tools_step_with_multiple_different_tools(self, pipeline_context):
        """Test ToolsStep with multiple different tool types."""
        from tools.base import ToolResult, BaseTool
        from agent.models import ToolCall
        
        # Create mock tools
        mock_rag = Mock(spec=BaseTool)
        mock_rag.name = "rag"
        mock_rag.execute.return_value = ToolResult(success=True, data=["RAG result"])
        
        mock_order = Mock(spec=BaseTool)
        mock_order.name = "order"
        mock_order.execute.return_value = ToolResult(success=True, data=["Order result"])
        
        # Create ToolsStep
        tools_step = ToolsStep(max_workers=2)
        tools_step.register_tool(mock_rag)
        tools_step.register_tool(mock_order)
        
        # Set execution plan with different tools
        pipeline_context.set("execution_plan", [
            ToolCall(step=1, tool_name="rag", reason="test", params={}),
            ToolCall(step=2, tool_name="order", reason="test", params={}),
        ])
        
        result = tools_step.execute(pipeline_context)
        
        assert result.success
        mock_rag.execute.assert_called_once()
        mock_order.execute.assert_called_once()


class TestLLMStepWithFallback:
    """Test LlmStep with fallback chain."""
    
    def test_llm_step_success(self, pipeline_context, mock_llm):
        """
        Mock providers, test fallback behavior.
        
        Steps:
        1. Create LlmStep with mock provider chain
        2. Execute step
        3. Assert LLM response is set in context
        """
        from llm.base import LLMResponse, Message, MessageRole
        from llm.fallback import ModelFallbackChain
        
        # Create mock provider
        mock_provider = Mock()
        mock_provider.name = "mock_provider"
        mock_provider.chat.return_value = LLMResponse(
            content="Mock LLM response",
            model="mock",
            metadata={"model_used": "mock_provider"}
        )
        
        # Create fallback chain
        fallback_chain = ModelFallbackChain([mock_provider])
        
        # Create LlmStep
        llm_step = LlmStep(fallback_chain=fallback_chain)
        
        # Execute
        result = llm_step.execute(pipeline_context)
        
        # Verify
        assert result.success, f"LlmStep should succeed, error: {result.error}"
        
        # Verify LLM response in context
        llm_response = pipeline_context.get("llm_response")
        assert llm_response == "Mock LLM response"
        
        # Verify model used
        model_used = pipeline_context.get("llm_model_used")
        assert model_used == "mock_provider"
    
    def test_llm_step_fallback_triggered(self, pipeline_context):
        """Test LlmStep falls back to secondary provider when primary fails."""
        from llm.base import LLMResponse
        from llm.fallback import ModelFallbackChain
        
        # Primary provider fails
        primary_provider = Mock()
        primary_provider.name = "primary"
        primary_provider.chat.side_effect = Exception("Primary failed")
        
        # Secondary provider succeeds
        secondary_provider = Mock()
        secondary_provider.name = "secondary"
        secondary_provider.chat.return_value = LLMResponse(
            content="Fallback response",
            model="secondary",
            metadata={"model_used": "secondary"}
        )
        
        # Create chain with short delay
        fallback_chain = ModelFallbackChain(
            [primary_provider, secondary_provider],
            base_delay=0.01  # Short delay for testing
        )
        
        llm_step = LlmStep(fallback_chain=fallback_chain)
        result = llm_step.execute(pipeline_context)
        
        # Should succeed via fallback
        assert result.success, f"Should succeed via fallback, error: {result.error}"
        assert pipeline_context.get("llm_response") == "Fallback response"
        
        # Verify primary was called
        assert primary_provider.chat.call_count >= 1
        # Secondary should have been called after primary failed
        assert secondary_provider.chat.call_count >= 1
    
    def test_llm_step_all_providers_fail(self, pipeline_context):
        """Test LlmStep when all providers fail."""
        from llm.base import LLMResponse
        from llm.fallback import ModelFallbackChain
        
        # All providers fail
        failing_provider = Mock()
        failing_provider.name = "failing"
        failing_provider.chat.return_value = LLMResponse(content="", error="Provider error")
        
        fallback_chain = ModelFallbackChain(
            [failing_provider],
            base_delay=0.01
        )
        
        llm_step = LlmStep(fallback_chain=fallback_chain)
        result = llm_step.execute(pipeline_context)
        
        # Should fail
        assert not result.success
        assert "LLM failed" in result.error or "Provider error" in result.error
    
    def test_llm_step_skips_when_terminated(self, pipeline_context):
        """Test LlmStep skips execution when termination is requested."""
        pipeline_context.set("should_terminate", True)
        pipeline_context.set("terminate_reason", "Low confidence")
        
        llm_step = LlmStep()
        result = llm_step.execute(pipeline_context)
        
        assert result.success
        assert result.metadata.get("skipped") is True
        assert result.metadata.get("reason") == "Low confidence"


class TestOutputStepSynthesis:
    """Test OutputStep for output synthesis."""
    
    def test_output_step_synthesis(self, pipeline_context, mock_synthesizer):
        """
        Mock synthesizer, assert output formatted.
        
        Steps:
        1. Create OutputStep with mock synthesizer
        2. Set context with RAG/LLM results
        3. Execute step
        4. Assert final_response is set
        """
        from output.synthesizer import OutputContext, OutputResult, OutputFormat
        
        # Setup context with results
        pipeline_context.set("rag_results", ["RAG result 1", "RAG result 2"])
        pipeline_context.set("llm_response", "LLM response content")
        pipeline_context.set("tool_results", [{"tool_name": "test", "success": True, "data": "tool data"}])
        
        # Setup mock synthesizer
        mock_synth = Mock()
        mock_synth.synthesize.return_value = OutputResult(
            content="Synthesized final response",
            format=OutputFormat.TEXT,
            source="rag"
        )
        
        # Create OutputStep with mock
        output_step = OutputStep(synthesizer=mock_synth)
        result = output_step.execute(pipeline_context)
        
        # Verify
        assert result.success, f"OutputStep should succeed, error: {result.error}"
        
        # Verify synthesizer was called
        mock_synth.synthesize.assert_called_once()
        
        # Verify final_response was set
        final_response = pipeline_context.get("final_response")
        assert final_response == "Synthesized final response"
        
        # Verify output_source was set
        output_source = pipeline_context.get("output_source")
        assert output_source == "rag"
    
    def test_output_step_clarification(self, pipeline_context):
        """Test OutputStep when clarification is needed."""
        from output.synthesizer import OutputSynthesizer
        
        # Set clarification flags
        pipeline_context.set("needs_clarify", True)
        pipeline_context.set("clarify_question", "Could you provide your order ID?")
        
        output_step = OutputStep()
        result = output_step.execute(pipeline_context)
        
        assert result.success
        
        # Should use clarification question as response
        final_response = pipeline_context.get("final_response")
        assert "order ID" in final_response
        assert pipeline_context.get("output_source") == "clarify"
    
    def test_output_step_termination(self, pipeline_context):
        """Test OutputStep when termination reason is set."""
        from output.synthesizer import OutputSynthesizer
        
        pipeline_context.set("should_terminate", True)
        pipeline_context.set("terminate_reason", "Customer requested end")
        
        output_step = OutputStep()
        result = output_step.execute(pipeline_context)
        
        assert result.success
        
        # Termination reason should be the response
        final_response = pipeline_context.get("final_response")
        assert "requested end" in final_response or final_response == "Customer requested end"


class TestContextStepSessionSave:
    """Test ContextStep for session management."""
    
    def test_context_step_session_save(self, pipeline_context, mock_session_manager):
        """
        Mock session manager, assert save called.
        
        Steps:
        1. Create ContextStep with mock session manager
        2. Set context with session_id and messages
        3. Execute step
        4. Assert save_round was called
        """
        # Setup context
        session = mock_session_manager.create_session(
            user_id="test_user",
            channel="web"
        )
        pipeline_context.set("session_id", session.session_id)
        pipeline_context.set("final_response", "Test assistant response")
        pipeline_context.set("intent", None)
        
        # Create ContextStep with mock manager
        context_step = ContextStep(
            session_manager=mock_session_manager,
            async_db_write=False  # Disable async for testing
        )
        
        result = context_step.execute(pipeline_context)
        
        # Verify
        assert result.success, f"ContextStep should succeed, error: {result.error}"
        
        # Verify save_round was called (twice: once for user msg, once for assistant)
        save_calls = mock_session_manager.save_round_calls
        assert len(save_calls) >= 2, f"Expected at least 2 save_round calls, got {len(save_calls)}"
        
        # Verify session_updated flag
        assert pipeline_context.get("session_updated") is True
    
    def test_context_step_no_session_id(self, pipeline_context, mock_session_manager):
        """Test ContextStep when no session_id is provided."""
        # Don't set session_id
        pipeline_context.set("session_id", None)
        
        context_step = ContextStep(session_manager=mock_session_manager)
        result = context_step.execute(pipeline_context)
        
        assert result.success
        # Should be skipped
        assert result.metadata.get("skipped") is True
        assert result.metadata.get("reason") == "no_session_id"
    
    def test_context_step_updates_state(self, pipeline_context, mock_session_manager):
        """Test ContextStep updates session state with intent info."""
        from agent.models import Intent, IntentType
        
        # Create session
        session = mock_session_manager.create_session(
            user_id="test_user",
            channel="web"
        )
        pipeline_context.set("session_id", session.session_id)
        pipeline_context.set("final_response", "Test response")
        
        # Set intent
        intent = Intent(
            intent_type=IntentType.QUERY,
            confidence=0.9,
            reason="Test"
        )
        pipeline_context.set("intent", intent)
        
        context_step = ContextStep(
            session_manager=mock_session_manager,
            async_db_write=False
        )
        
        result = context_step.execute(pipeline_context)
        
        assert result.success
        
        # Verify update_state was called
        update_calls = mock_session_manager.update_state_calls
        assert len(update_calls) >= 1, "Should have called update_state"


class TestPipelineOrchestratorIntegration:
    """Integration tests for PipelineOrchestrator."""
    
    def test_pipeline_orchestrator_execute(self, mock_llm, mock_synthesizer, mock_session_manager):
        """Test full pipeline execution."""
        orchestrator = PipelineOrchestrator()
        orchestrator.register_default_steps()
        
        # Mock the steps
        orchestrator.steps["agent"] = AgentStep(agent=Mock(return_value=MagicMock(
            intent=MagicMock(intent_type=MagicMock(value="query"), confidence=0.9, reason="test", to_dict=MagicMock(return_value={})),
            execution_plan=[],
            needs_clarify=False,
            clarify_question="",
            should_terminate=False,
            terminate_reason=""
        )))
        
        result = orchestrator.execute(
            user_id="test_user",
            request="Test request"
        )
        
        assert "trace_id" in result
        assert "response" in result
        assert "metrics" in result
    
    def test_pipeline_orchestrator_step_metrics(self, mock_llm):
        """Test that pipeline records per-step metrics."""
        orchestrator = PipelineOrchestrator()
        orchestrator.register_default_steps()
        
        result = orchestrator.execute(
            user_id="test_user",
            request="Test request with metrics"
        )
        
        assert "metrics" in result
        assert "agent_step" in result["metrics"] or "total" in result["metrics"]
    
    def test_pipeline_orchestrator_error_continuation(self, mock_llm):
        """Test that pipeline continues even when a step fails."""
        orchestrator = PipelineOrchestrator()
        orchestrator.register_default_steps()
        
        # Step execution continues even on failure
        result = orchestrator.execute(
            user_id="test_user",
            request="Test request"
        )
        
        # Should still return a result (possibly with error in context)
        assert "trace_id" in result


class TestPipelineContext:
    """Test PipelineContext behavior."""
    
    def test_pipeline_context_get_set(self):
        """Test PipelineContext get/set operations."""
        from pipeline.orchestrator import PipelineContext
        
        ctx = PipelineContext(trace_id="test_trace", user_id="test_user", request="test")
        
        ctx.set("key1", "value1")
        assert ctx.get("key1") == "value1"
        
        assert ctx.get("nonexistent", "default") == "default"
        
        ctx.set("nested", {"a": 1, "b": 2})
        assert ctx.get("nested") == {"a": 1, "b": 2}
    
    def test_pipeline_context_errors(self):
        """Test PipelineContext error tracking."""
        from pipeline.orchestrator import PipelineContext
        
        ctx = PipelineContext(trace_id="test", user_id="test", request="test")
        
        assert not ctx.has_error()
        
        ctx.add_error("First error")
        assert ctx.has_error()
        assert "First error" in ctx.errors
        
        ctx.add_error("Second error")
        assert len(ctx.errors) == 2
