"""
混合检索器 - 多路召回 + RRF 融合

混合检索的核心思想：
单一检索方式（BM25 或向量检索）都有局限性：
- BM25：擅长精确词匹配，但无法捕捉语义相似度
- 向量检索：擅长语义相似度，但可能遗漏关键词

多路召回结合两者优点：
1. BM25 检索 - 精确关键词匹配
2. 向量检索 - 语义相似度
3. RRF 融合 - 倒数排名融合

RRF (Reciprocal Rank Fusion) 公式：
RRF_score(d) = Σ 1/(k + rank(d))

其中 k 是融合参数（通常 60），rank(d) 是该文档在不同检索结果中的排名。

配置：自动读取 rag/config.json
"""

import os
import json
import numpy as np
from pathlib import Path


def load_config() -> dict:
    """读取配置文件"""
    config_path = Path(__file__).parent / "config.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# 读取配置
_config = load_config()
_rag_config = _config.get("rag", {})
_storage_config = _rag_config.get("storage", {})
_embedding_config = _rag_config.get("embedding", {})

# 默认配置
DEFAULT_PERSIST_DIR = _storage_config.get("persist_directory", "./data")
DEFAULT_EMBEDDING_MODEL = _embedding_config.get("model", "BAAI/bge-small-zh-v1.5")
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass, field

from .bm25 import BM25Retriever
from .vector_store import ChromaVectorStore
from .embedding import SentenceEmbeddingFunction, MockEmbeddingFunction
from .advanced_chunker import HierarchicalChunker, TextChunk


@dataclass
class RetrievalItem:
    """
    检索结果项

    包含单条检索结果的所有信息。

    Attributes:
        content: 文档内容
        source: 来源（如文件名）
        score: RRF 融合分数
        rank: 融合后的排名
        metadata: 额外元数据
    """

    content: str  # 文档内容
    source: str  # 来源
    score: float  # RRF 分数
    rank: int = 0  # 融合后排名
    metadata: dict = field(default_factory=dict)  # 元数据

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "content": self.content,
            "source": self.source,
            "score": self.score,
            "rank": self.rank,
            "metadata": self.metadata,
        }


class HybridRetriever:
    """
    混合检索器

    结合 BM25 和向量检索，通过 RRF 融合得到最终结果。

    工作流程：
    1. 用户输入查询
    2. 并行执行 BM25 和向量检索
    3. 分别得到两个排序结果
    4. 使用 RRF 融合两个排序
    5. 返回融合后的 top_k 结果

    使用示例：
        retriever = HybridRetriever(
            embedding_model="BAAI/bge-small-zh-v1.5",
            persist_directory="./data"
        )
        retriever.load_knowledge([("文档内容", "来源")])
        results = retriever.retrieve("查询", top_k=3)
    """

    def __init__(
        self,
        vector_top_k: int = _rag_config.get("retrieval", {}).get("vector_top_k", 10),
        bm25_top_k: int = _rag_config.get("retrieval", {}).get("bm25_top_k", 10),
        fusion_top_k: int = _rag_config.get("retrieval", {}).get("fusion_top_k", 5),
        rrf_k: int = _rag_config.get("retrieval", {}).get("rrf_k", 60),
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        persist_directory: Optional[str] = DEFAULT_PERSIST_DIR,
        min_chunk_size: int = 100,
        max_chunk_size: int = 800,
        semantic_threshold: float = 0.3,
    ):
        """
        初始化混合检索器

        Args:
            vector_top_k: 向量检索返回的候选数量
            bm25_top_k: BM25 检索返回的候选数量
            fusion_top_k: 融合后返回的最终数量
            rrf_k: RRF 融合参数，默认 60
            embedding_model: Embedding 模型名称或 "mock"
            persist_directory: 向量数据持久化目录
            min_chunk_size: 最小块大小
            max_chunk_size: 最大块大小
            semantic_threshold: 语义合并阈值
        """
        self.vector_top_k = vector_top_k
        self.bm25_top_k = bm25_top_k
        self.fusion_top_k = fusion_top_k
        self.rrk_k = rrf_k
        self.persist_directory = persist_directory

        # 初始化 Embedding
        if embedding_model == "mock":
            self.embedding_fn = MockEmbeddingFunction()
        else:
            self.embedding_fn = SentenceEmbeddingFunction(embedding_model)

        # 初始化向量存储
        self.vector_store = ChromaVectorStore(
            persist_directory=persist_directory, embedding_dim=self.embedding_fn.dim
        )

        # 初始化 BM25
        self.bm25_retriever = BM25Retriever()

        # 初始化分块器（使用config中的参数）
        self.chunker = HierarchicalChunker(
            min_chunk_size=min_chunk_size,
            max_chunk_size=max_chunk_size,
            semantic_threshold=semantic_threshold,
        )

        # 保存分块后的文本块
        self._chunks: List[TextChunk] = []
        self._initialized = False

    @property
    def embedding_dim(self) -> int:
        """向量维度"""
        return self.embedding_fn.dim

    def load_knowledge(self, documents: List[Tuple[str, str]]):
        """
        加载知识库文档

        执行步骤：
        1. 文本分块
        2. 添加到 BM25 索引
        3. 生成向量并存入 Chroma

        Args:
            documents: 文档列表 List[(content, source)]
        """
        # 1. 文本分块
        self._chunks = self.chunker.chunk_documents(documents)

        # 2. 添加到 BM25
        bm25_docs = [(c.content, c.source) for c in self._chunks]
        self.bm25_retriever.add_documents(bm25_docs)

        # 3. 生成向量
        texts = [c.content for c in self._chunks]
        embeddings = self.embedding_fn.embed_batch(texts)

        # 4. 构建 Document 对象
        from .models import Document

        docs = [
            Document(content=c.content, source=c.source, metadata=c.metadata)
            for c in self._chunks
        ]

        # 5. 存入 Chroma
        ids = [f"chunk_{i}" for i in range(len(docs))]
        self.vector_store.add_documents(docs, embeddings, ids)

        self._initialized = True

    def retrieve(self, query: str, top_k: int = 3) -> List[str]:
        """
        检索接口 - 返回纯内容列表

        符合需求规范：rag.retrieve(query) -> list[str]

        Args:
            query: 查询文本
            top_k: 返回结果数量

        Returns:
            List[str]: 相关文档内容列表
        """
        results = self.retrieve_with_scores(query, top_k)
        return [item.content for item in results]

    def retrieve_with_scores(self, query: str, top_k: int = 3) -> List[RetrievalItem]:
        """
        带分数的检索接口

        Args:
            query: 查询文本
            top_k: 返回结果数量

        Returns:
            List[RetrievalItem]: 检索结果列表，按分数降序
        """
        if not self._initialized:
            return []

        # 1. BM25 检索
        bm25_results = self._bm25_search(query)

        # 2. 向量检索
        vector_results = self._vector_search(query)

        # 3. RRF 融合
        fused = self._rrf_fusion(bm25_results, vector_results)

        return fused[:top_k]

    def _bm25_search(self, query: str) -> Dict[str, Tuple[float, int]]:
        """
        BM25 搜索

        Returns:
            Dict[str, (score, rank)]
            - key: 文档内容
            - value: (BM25分数, 排名)
        """
        results = self.bm25_retriever.search(query, self.bm25_top_k)

        ranked = {}
        for rank, (content, score, source) in enumerate(results):
            ranked[content] = (score, rank + 1)

        return ranked

    def _vector_search(self, query: str) -> Dict[str, Tuple[float, int]]:
        """
        向量搜索

        Returns:
            Dict[str, (score, rank)]
            - key: 文档内容
            - value: (相似度分数, 排名)
        """
        # 将查询文本转为向量
        query_embedding = self.embedding_fn.embed_text(query)

        # 向量检索
        results = self.vector_store.search(query_embedding, self.vector_top_k)

        ranked = {}
        for rank, doc in enumerate(results):
            ranked[doc.content] = (doc.score, rank + 1)

        return ranked

    def _rrf_fusion(
        self,
        bm25_results: Dict[str, Tuple[float, int]],
        vector_results: Dict[str, Tuple[float, int]],
    ) -> List[RetrievalItem]:
        """
        RRF (Reciprocal Rank Fusion) 融合

        RRF 是一种简单而有效的多检索结果融合方法。
        核心思想：排名越靠前的结果越重要。

        公式：RRF_score(d) = Σ 1/(k + rank(d))

        优点：
        1. 无需训练，直接使用排名信息
        2. 对检索方式无假设，适用于各种检索系统
        3. 简单高效，只需排序即可

        Args:
            bm25_results: BM25 检索结果 {content: (score, rank)}
            vector_results: 向量检索结果 {content: (score, rank)}

        Returns:
            List[RetrievalItem]: 融合后的结果列表
        """
        # 合并两个结果的所有文档
        all_contents = set(bm25_results.keys()) | set(vector_results.keys())

        # 初始化 RRF 分数
        rrf_scores: Dict[str, float] = {content: 0.0 for content in all_contents}

        # BM25 贡献的 RRF 分数
        for content, (score, rank) in bm25_results.items():
            rrf_scores[content] += 1.0 / (self.rrk_k + rank)

        # 向量检索贡献的 RRF 分数
        for content, (score, rank) in vector_results.items():
            rrf_scores[content] += 1.0 / (self.rrk_k + rank)

        # 按 RRF 分数降序排序
        sorted_contents = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

        # 构建结果列表
        results = []
        for rank, (content, rrf_score) in enumerate(
            sorted_contents[: self.fusion_top_k * 2]
        ):
            # 查找来源
            source = "unknown"
            for chunk in self._chunks:
                if chunk.content == content:
                    source = chunk.source
                    break

            results.append(
                RetrievalItem(
                    content=content,
                    source=source,
                    score=rrf_score,
                    rank=rank + 1,
                    metadata={"rrf_score": rrf_score},
                )
            )

        return results

    def clear(self):
        """清空知识库"""
        self._chunks = []
        self._initialized = False
        self.vector_store.clear()
        self.bm25_retriever = BM25Retriever()

    def count(self) -> int:
        """知识库文档数量"""
        return len(self._chunks)


# 按 channel 缓存的检索器
_retrievers: Dict[str, HybridRetriever] = {}


def get_retriever(
    channel: str = None, persist_directory: str = None
) -> HybridRetriever:
    """
    获取指定渠道的混合检索器

    每个 channel 独立缓存，确保：
    1. 只加载一次模型
    2. 只初始化一次知识库
    3. 内存中每个 channel 只有一份向量数据

    Args:
        channel: 渠道名称（如 xianyu, web, feishu）
        persist_directory: 持久化目录（如果不传，从 channel 配置获取）

    Returns:
        HybridRetriever 实例
    """
    from config.channel_manager import (
        get_channel_config,
        load_knowledge,
        get_vector_store_path,
    )

    global _retrievers

    # 如果没传 channel，使用默认
    if channel is None:
        channel = "xianyu"

    # 如果已缓存，直接返回
    if channel in _retrievers:
        return _retrievers[channel]

    # 如果没传 persist_directory，从 channel 配置获取
    if persist_directory is None:
        persist_directory = get_vector_store_path(channel)

    if persist_directory is None:
        persist_directory = DEFAULT_PERSIST_DIR

    # 创建新的检索器
    from config.settings import get_settings

    settings = get_settings()
    retriever = HybridRetriever(
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        persist_directory=persist_directory,
        min_chunk_size=settings.rag_chunk_min_size,
        max_chunk_size=settings.rag_chunk_max_size,
        semantic_threshold=settings.rag_semantic_threshold,
    )

    # 从 channel 的 knowledge.txt 加载知识
    _init_channel_knowledge(retriever, channel)

    _retrievers[channel] = retriever
    return retriever


def _init_channel_knowledge(retriever: HybridRetriever, channel: str):
    """
    从 channel 的 knowledge.txt 加载知识库
    """
    from config.channel_manager import load_knowledge

    # 清空向量库
    retriever.clear()

    # 加载 channel 对应的知识
    docs = load_knowledge(channel)
    if docs:
        retriever.load_knowledge(docs)


def _init_default_knowledge(retriever: HybridRetriever):
    """
    初始化默认知识库

    每次都清空向量库后重建，避免重复添加导致数据膨胀。
    """
    # 清空向量库，只重建数据
    retriever.clear()

    default_docs = [
        (
            "我们的退货政策是7天内无理由退货，需保持商品完好。退货时请联系客服申请。",
            "退货政策",
        ),
        ("订单发货后1-3天可查看物流信息，请点击订单详情查看物流动态。", "物流查询"),
        (
            "商品价格以页面显示为准，下单时可享受当前优惠活动，更多折扣请关注我们的促销页面。",
            "价格说明",
        ),
        ("会员积分可用于抵扣订单金额，1积分=1分钱，积分越多抵扣越多。", "会员积分"),
        (
            "客服工作时间为工作日9:00-18:00，非工作时间请留言，我们会尽快回复。",
            "客服时间",
        ),
        ("支持多种支付方式，包括微信支付、支付宝、银行卡支付，安全便捷。", "支付方式"),
        ("全场满99元包邮，不满99元收取10元运费，部分偏远地区除外。", "物流费用"),
    ]
    retriever.load_knowledge(default_docs)


def retrieve(query: str, top_k: int = 3) -> list[str]:
    """
    便捷接口 - 符合需求规范的检索函数

    用法：
        from rag import retrieve
        results = retrieve("退货政策", top_k=3)
        # results = ["退货政策是...", "会员积分...", ...]

    Args:
        query: 查询文本
        top_k: 返回结果数量

    Returns:
        List[str]: 相关文档内容列表
    """
    return get_retriever().retrieve(query, top_k)
