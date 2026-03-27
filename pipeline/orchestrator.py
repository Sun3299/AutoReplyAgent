"""
Pipeline 编排器

核心编排器，执行流水线步骤。
"""

from typing import List, Dict, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from .step import Step, StepResult, StepType
from .trace import TraceManager, Trace, TraceStatus
from .retry import ExponentialBackoff, RetryConfig
from .fallback import FallbackPolicy, FallbackOption

# Import all 5 steps
from pipeline.steps import AgentStep, ToolsStep, LlmStep, OutputStep, ContextStep


class PipelineContext:
    """
    Pipeline上下文
    
    在步骤间传递数据。
    
    Attributes:
        trace_id: 链路ID
        user_id: 用户ID
        request: 用户请求
        response: 系统回复
        data: 步骤间共享数据
        errors: 收集的错误
    """
    
    def __init__(self, trace_id: str, user_id: str = "", request: str = ""):
        self.trace_id = trace_id
        self.user_id = user_id
        self.request = request
        self.response = ""
        self.data: Dict[str, Any] = {}
        self.errors: List[str] = []
    
    def set(self, key: str, value: Any):
        self.data[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)
    
    def add_error(self, error: str):
        self.errors.append(error)
    
    def has_error(self) -> bool:
        return len(self.errors) > 0


class PipelineResult:
    """
    Pipeline执行结果
    
    Attributes:
        success: 是否成功
        response: 最终回复
        context: Pipeline上下文
        trace: 链路信息
        metrics: 性能指标
    """
    
    def __init__(self, success: bool, context: PipelineContext, trace: Optional[Trace] = None):
        self.success = success
        self.response = context.response
        self.context = context
        self.trace = trace
        self.metrics = {
            "total_duration": 0.0,
            "steps": {},
        }
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "response": self.response,
            "trace_id": self.context.trace_id,
            "errors": self.context.errors,
            "metrics": self.metrics,
        }


class PipelineOrchestrator:
    """
    Pipeline编排器
    
    串联所有Step执行，支持：
    - 并行执行工具步骤
    - 失败跳过/降级
    - 链路追踪
    - 超时控制
    
    使用示例：
        orchestrator = PipelineOrchestrator()
        
        # 添加步骤
        orchestrator.add_step(AgentStep())
        orchestrator.add_step(ToolsStep())
        orchestrator.add_step(LlmStep())
        orchestrator.add_step(OutputStep())
        orchestrator.add_step(ContextStep())
        
        # 执行
        result = orchestrator.execute("user123", "查订单")
    """
    
    def __init__(
        self,
        trace_manager: Optional[TraceManager] = None,
        max_workers: int = 4,
    ):
        self.steps: Dict[str, Step] = {}
        self.step_order: List[str] = []
        self.trace_manager = trace_manager or TraceManager()
        self.max_workers = max_workers
    
    def register_default_steps(self):
        """Register the 5 default steps in order: Agent → Tools → LLM → Output → Context"""
        self.steps["agent"] = AgentStep()
        self.step_order.append("agent")
        self.steps["tools"] = ToolsStep()
        self.step_order.append("tools")
        self.steps["llm"] = LlmStep()
        self.step_order.append("llm")
        self.steps["output"] = OutputStep()
        self.step_order.append("output")
        self.steps["context"] = ContextStep()
        self.step_order.append("context")
    
    def add_step(self, step: Step):
        """Add a step to the pipeline"""
        self.steps[step.name] = step
        self.step_order.append(step.name)
    
    def execute(
        self,
        user_id: str,
        request: str,
        trace_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute the pipeline with trace_id propagation and per-step metrics.
        
        Args:
            user_id: User ID
            request: User request message
            trace_id: Trace ID (generated if not provided)
            context: Initial context data
            
        Returns:
            ChatResponse-compatible dict: {trace_id, response, sources, metrics, error}
        """
        import uuid
        if trace_id is None:
            trace_id = str(uuid.uuid4())
        
        # Create pipeline context
        ctx = PipelineContext(trace_id, user_id, request)
        ctx.trace_id = trace_id
        if context:
            for k, v in context.items():
                ctx.set(k, v)
        
        # Start trace
        trace = self.trace_manager.start_trace(user_id, request, trace_id)
        
        # Execute steps in order
        step_metrics: Dict[str, float] = {}
        total_start = time.time()
        
        # Execute each step in order, continuing even if one fails
        for step_name in self.step_order:
            step = self.steps.get(step_name)
            if step is None:
                continue
                
            step_start = time.time()
            step_result = self._execute_step(step, ctx)
            step_duration = time.time() - step_start
            
            # Record duration in milliseconds
            step_metrics[step_name] = round(step_duration * 1000, 2)
            
            # Collect errors but continue execution
            if not step_result.success and not step.optional:
                ctx.add_error(step_result.error)
        
        total_duration = time.time() - total_start
        step_metrics["total"] = round(total_duration * 1000, 2)
        
        # Extract response
        response = ctx.get("final_response", "抱歉，该回答无法提供")
        
        # Build sources list
        sources: List[str] = []
        if ctx.get("rag_results"):
            sources.append("rag")
        if ctx.get("tool_results"):
            sources.append("tool")
        
        # Get error
        error = ctx.errors[-1] if ctx.has_error() else None
        
        # Finish trace
        try:
            trace.finish(status=TraceStatus.SUCCESS if not error else TraceStatus.ERROR)
        except Exception:
            pass
        
        # Build ChatResponse-compatible result
        return {
            "trace_id": trace_id,
            "response": response,
            "sources": sources,
            "metrics": step_metrics,
            "error": error,
        }
    
    def _execute_step(self, step: Step, ctx: PipelineContext) -> StepResult:
        """Execute a single step with trace span."""
        start = time.time()
        
        # Create span for this step
        span = self.trace_manager.add_span(step.name)
        
        try:
            # Execute the step (all steps handle their own internal parallelization)
            result = step.execute(ctx)
            
            span.finish(status=TraceStatus.SUCCESS)
            return result
            
        except Exception as e:
            span.finish(status=TraceStatus.ERROR, error=str(e))
            return StepResult(
                success=False,
                error=f"Step {step.name} failed: {e}",
                step_name=step.name,
                step_type=step.step_type.value,
                duration=time.time() - start,
            )
    
    def execute_with_retry(
        self,
        user_id: str,
        request: str,
        trace_id: Optional[str] = None,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """Execute with retry logic."""
        retry_policy = ExponentialBackoff(RetryConfig(max_attempts=max_retries))
        
        last_error = None
        for attempt in range(max_retries):
            try:
                return self.execute(user_id, request, trace_id=trace_id)
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = retry_policy.get_delay(attempt)
                    time.sleep(delay)
        
        # All retries failed - return error response
        return {
            "trace_id": trace_id or "",
            "response": "服务暂时不可用，请稍后重试",
            "sources": [],
            "metrics": {},
            "error": str(last_error) if last_error else "Unknown error",
        }
