"""
Tools Step - 工具执行步骤

根据 channel 执行对应的工具。

输入：
    - ctx.get("execution_plan"): 执行计划（ToolCall 列表）
    - ctx.get("channel"): 渠道名称

输出：
    - ctx.set("tool_results", [...]): 工具执行结果列表
    - ctx.set("rag_results", [...]): RAG 结果（如果执行了 RAG）
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional, TYPE_CHECKING
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from pipeline.step import Step, StepResult, StepType
from tools.base import BaseTool, ToolResult
from tools.rag_tool import RagTool
from tools.channels.registry import get_channel_tools

if TYPE_CHECKING:
    from pipeline.orchestrator import PipelineContext


class ToolsStep(Step):
    """
    工具执行步骤
    
    负责：
    1. 从执行计划提取工具调用
    2. 根据 channel 加载对应平台的工具
    3. 并发执行工具
    4. 聚合结果
    
    使用示例：
        step = ToolsStep()
        result = step.execute(ctx)
    """
    
    def __init__(
        self,
        max_workers: int = 4,
    ):
        """
        初始化 Tools 步骤
        
        Args:
            max_workers: 最大并发数
        """
        super().__init__("tools_step", StepType.TOOLS, optional=True, timeout=60)
        self._max_workers = max_workers
        self._tools: Dict[str, BaseTool] = {}
        self._channel: str = "web"
    
    def _register_tools_for_channel(self, channel: str):
        """根据 channel 注册工具"""
        self._channel = channel
        self._tools = {}
        
        # 获取该 channel 的所有工具
        channel_tools = get_channel_tools(channel)
        
        for tool_name, tool in channel_tools.items():
            self._tools[tool_name] = tool
        
        # 如果没有 RAG 工具，注册一个
        if "rag" not in self._tools:
            self._tools["rag"] = RagTool(default_top_k=5, channel=channel)
    
    def register_tool(self, tool: BaseTool):
        """
        注册工具
        
        Args:
            tool: 工具实例
        """
        self._tools[tool.name] = tool
    
    def _do_execute(self, ctx: 'PipelineContext') -> StepResult:
        """
        执行工具调用
        
        Args:
            ctx: Pipeline上下文
            
        Returns:
            StepResult: 执行结果
        """
        start_time = time.time()
        
        # 根据 channel 加载工具
        channel = ctx.get("channel", "web")
        self._register_tools_for_channel(channel)
        
        all_results: List[Dict[str, Any]] = []
        
        try:
            # 获取执行计划
            execution_plan = ctx.get("execution_plan", [])
            
            # 如果没有执行计划，跳过
            if not execution_plan:
                return StepResult(
                    success=True,
                    data=[],
                    step_name=self.name,
                    step_type=self.step_type.value,
                    duration=time.time() - start_time,
                    metadata={
                        "message": "No execution plan, skipping tools",
                        "duration_ms": int((time.time() - start_time) * 1000),
                    }
                )
            
            # 过滤出需要执行的工具调用（排除特殊标记）
            tool_calls = []
            for call in execution_plan:
                # 跳过置信度检查等内部标记
                if call.tool_name.startswith("_"):
                    continue
                tool_calls.append(call)
            
            if not tool_calls:
                return StepResult(
                    success=True,
                    data=[],
                    step_name=self.name,
                    step_type=self.step_type.value,
                    duration=time.time() - start_time,
                    metadata={
                        "message": "No valid tool calls, skipping",
                        "duration_ms": int((time.time() - start_time) * 1000),
                    }
                )
            
            # 并发执行工具
            results = self._execute_tools_parallel(tool_calls)
            
            # 聚合结果
            for result in results:
                all_results.append({
                    "tool_name": result.get("tool_name", ""),
                    "success": result.get("success", False),
                    "data": result.get("data"),
                    "error": result.get("error", ""),
                })
            
            # 分离 RAG 结果和其他工具结果
            rag_results = []
            other_results = []
            
            for r in all_results:
                if r.get("tool_name") == "rag":
                    rag_results.extend(r.get("data", []) if r.get("success") else [])
                else:
                    other_results.append(r)
            
            # 设置到上下文
            ctx.set("tool_results", other_results)
            ctx.set("rag_results", rag_results)
            
            # 计算成功数量
            success_count = sum(1 for r in all_results if r.get("success", False))
            
            duration = time.time() - start_time
            
            return StepResult(
                success=success_count > 0,
                data=all_results,
                step_name=self.name,
                step_type=self.step_type.value,
                duration=duration,
                metadata={
                    "total_tools": len(tool_calls),
                    "success_count": success_count,
                    "rag_result_count": len(rag_results),
                    "duration_ms": int(duration * 1000),
                }
            )
            
        except Exception as e:
            duration = time.time() - start_time
            return StepResult(
                success=False,
                error=f"ToolsStep failed: {type(e).__name__}: {str(e)}",
                step_name=self.name,
                step_type=self.step_type.value,
                duration=duration,
                metadata={
                    "error_type": type(e).__name__,
                    "duration_ms": int(duration * 1000),
                }
            )
    
    def _execute_tools_parallel(
        self,
        tool_calls: List[Any],
    ) -> List[Dict[str, Any]]:
        """
        并发执行工具
        
        Args:
            tool_calls: 工具调用列表
            
        Returns:
            执行结果列表
        """
        results: List[Dict[str, Any]] = []
        
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {
                executor.submit(self._execute_single_tool, call): call
                for call in tool_calls
            }
            
            for future in as_completed(futures):
                call = futures[future]
                try:
                    result = future.result()
                    results.append({
                        "tool_name": call.tool_name,
                        "success": result.success,
                        "data": result.data,
                        "error": result.error or "",
                    })
                except Exception as e:
                    results.append({
                        "tool_name": call.tool_name,
                        "success": False,
                        "data": None,
                        "error": f"Execution failed: {str(e)}",
                    })
        
        return results
    
    def _execute_single_tool(self, tool_call: Any) -> ToolResult:
        """
        执行单个工具
        
        Args:
            tool_call: 工具调用对象
            
        Returns:
            ToolResult
        """
        tool_name = tool_call.tool_name
        params = tool_call.params or {}
        
        # 获取工具
        tool = self._tools.get(tool_name)
        
        if tool is None:
            return ToolResult(
                success=False,
                error=f"Tool not found: {tool_name}",
            )
        
        # 执行工具
        return tool.execute(**params)
