"""
RAG Tool - 知识库检索工具

调用 hybrid_retriever 实现真实的 RAG 检索功能。
"""

from typing import Any, Dict, List

from tools.base import BaseTool, ToolResult, ToolType


class RagTool(BaseTool):
    """
    RAG 检索工具

    使用混合检索器进行知识库查询，返回相关文档内容。

    属性说明：
    - name: 工具唯一标识 "rag_tool"
    - description: 工具描述，用于 LLM 理解工具用途
    - tool_type: 工具类型，默认 QUERY（只读操作）

    使用示例：
        tool = RagTool()
        result = tool.execute(query="退货政策", top_k=5)
        if result.success:
            for doc in result.data:
                print(doc)
    """

    def __init__(self, default_top_k: int = 5, channel: str = "web"):
        """
        初始化 RAG 工具

        Args:
            default_top_k: 默认返回结果数量
            channel: 渠道名称，用于加载对应渠道的向量库
        """
        self._default_top_k = default_top_k
        self._channel = channel

    @property
    def name(self) -> str:
        """工具名称"""
        return "rag"

    @property
    def description(self) -> str:
        """
        工具描述

        返回内容：知识库检索结果列表，每条为相关文档内容。
        """
        return "RAG知识库查询工具，用于检索相关文档"

    @property
    def tool_type(self) -> ToolType:
        """工具类型为查询类"""
        return ToolType.QUERY

    @property
    def parameters(self) -> Dict[str, Any]:
        """
        参数定义

        JSON Schema 格式，用于 LLM 理解需要什么参数。
        """
        return {"top_k": {"type": "integer", "description": "返回结果数量"}}

    def execute(self, **params) -> ToolResult:
        """
        执行 RAG 检索

        Args:
            **params: 包含 query 和可选的 top_k

        Returns:
            ToolResult: 成功时 data 为文档列表（含content和source），失败时 error 包含错误信息
        """
        try:
            query = params.get("query", "")
            top_k = params.get("top_k", 5)

            # 根据 channel 获取对应的 retriever
            from rag.hybrid_retriever import get_retriever

            retriever = get_retriever(channel=self._channel)

            # 使用 retrieve_with_scores 获取完整结果（含 source）
            # 格式：{"content": "...", "source": "...", "score": 0.xx, "rank": 1}
            results = retriever.retrieve_with_scores(query, top_k)

            # 转换为字典列表返回，包含 content 和 source
            formatted_results = [
                {
                    "content": item.content,
                    "source": item.source,
                    "score": item.score,
                    "rank": item.rank,
                }
                for item in results
            ]

            # P2优化: 空结果降级查询
            if not formatted_results:
                fallback_queries = [
                    f"常见问题:{query}",
                    f"FAQ:{query}",
                    query,
                ]
                for fallback_q in fallback_queries:
                    fallback_results = retriever.retrieve_with_scores(fallback_q, top_k)
                    if fallback_results:
                        formatted_results = [
                            {
                                "content": item.content,
                                "source": item.source,
                                "score": item.score,
                                "rank": item.rank,
                                "fallback": True,  # 标记为降级查询结果
                            }
                            for item in fallback_results
                        ]
                        break

            return ToolResult(success=True, data=formatted_results, message="查询成功")
        except Exception as e:
            print(f"[RAG ERROR] {type(e).__name__}: {str(e)}", flush=True)
            return ToolResult(success=False, error=str(e))

    def validate_params(self, **params) -> tuple:
        """
        验证参数

        Args:
            **params: 待验证的参数

        Returns:
            (is_valid, error_message)
        """
        query = params.get("query")
        if not query:
            return False, "查询内容不能为空"

        if not isinstance(query, str):
            return False, "查询内容必须是字符串"

        top_k = params.get("top_k")
        if top_k is not None:
            if not isinstance(top_k, int):
                return False, "top_k 必须是整数"
            if top_k < 1 or top_k > 20:
                return False, "top_k 必须在 1-20 之间"

        return True, ""
