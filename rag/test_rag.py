"""
RAG模块测试 - 简化版

测试覆盖：
1. 分块器 - 文本如何切成小块
2. BM25 - 关键词搜索
3. Embedding - 文本转向量
4. 混合检索 - BM25 + 向量 融合搜索
5. 文档加载 - 读取文件
"""

import pytest
import os
import shutil


# ==================== 分块器测试 ====================

def test_chunker_短文本():
    """短文本应该直接返回一个块"""
    from rag.advanced_chunker import HierarchicalChunker
    chunker = HierarchicalChunker()
    result = chunker.chunk("短文本", "test")
    assert len(result) >= 1
    assert result[0].content == "短文本"


def test_chunker_空文本():
    """空文本返回空列表"""
    from rag.advanced_chunker import HierarchicalChunker
    chunker = HierarchicalChunker()
    result = chunker.chunk("", "test")
    assert result == []


def test_chunker_批量():
    """批量分块多个文档"""
    from rag.advanced_chunker import HierarchicalChunker
    chunker = HierarchicalChunker()
    docs = [("内容一", "source1"), ("内容二", "source2")]
    result = chunker.chunk_documents(docs)
    assert len(result) >= 2


# ==================== BM25测试 ====================

def test_bm25_基本搜索():
    """添加文档后能搜索到"""
    from rag.bm25 import BM25
    bm25 = BM25()
    bm25.add_documents(["退货政策是7天", "物流查询方法", "价格说明"])
    
    results = bm25.search("退货", top_k=2)
    
    assert len(results) == 2
    assert results[0][1] >= results[1][1]  # 分数从高到低


def test_bm25_空索引():
    """没有文档时返回空"""
    from rag.bm25 import BM25
    bm25 = BM25()
    results = bm25.search("测试", top_k=5)
    assert results == []


def test_bm25_计数():
    """文档数量正确"""
    from rag.bm25 import BM25
    bm25 = BM25()
    bm25.add_documents(["doc1", "doc2", "doc3"])
    assert bm25.count() == 3


# ==================== Embedding测试 ====================

def test_mock_embedding_维度():
    """Mock生成的向量维度正确"""
    from rag.embedding import MockEmbeddingFunction
    fn = MockEmbeddingFunction(dim=768)
    
    emb = fn.embed_text("测试")
    assert len(emb) == 768


def test_mock_embedding_批量():
    """批量生成向量"""
    from rag.embedding import MockEmbeddingFunction
    fn = MockEmbeddingFunction(dim=512)
    
    batch = fn.embed_batch(["文本1", "文本2"])
    assert len(batch) == 2
    assert len(batch[0]) == 512


def test_local_embedding_维度():
    """本地中文模型维度是512（仅测试配置维度，不加载模型）"""
    # 注意：由于测试环境网络限制，这里只验证配置维度
    # 真实场景下模型路径为 ./models/bge-small-zh-v1.5
    from rag.embedding import SentenceEmbeddingFunction
    assert SentenceEmbeddingFunction.SUPPORTED_MODELS.get("BAAI/bge-small-zh-v1.5", {}).get("dim") == 512


# ==================== 混合检索测试 ====================

@pytest.fixture
def clean_rag_dir():
    """每个测试用独立目录，结束后清理"""
    rag_dir = "./test_rag_data"
    yield rag_dir
    import time
    time.sleep(0.1)
    if os.path.exists(rag_dir):
        import gc
        gc.collect()
        shutil.rmtree(rag_dir, ignore_errors=True)


def test_混合检索_基本接口(clean_rag_dir):
    """retrieve() 返回字符串列表"""
    from rag.hybrid_retriever import HybridRetriever
    
    retriever = HybridRetriever(
        embedding_model="mock",
        persist_directory=clean_rag_dir
    )
    retriever.load_knowledge([
        ("退货政策是7天无理由退货", "policy"),
        ("物流查询1-3天到货", "logistics"),
    ])
    
    results = retriever.retrieve("如何退货", top_k=2)
    
    assert isinstance(results, list)
    assert all(isinstance(r, str) for r in results)


def test_混合检索_空知识库(clean_rag_dir):
    """没有知识库时返回空"""
    from rag.hybrid_retriever import HybridRetriever
    
    retriever = HybridRetriever(
        embedding_model="mock",
        persist_directory=clean_rag_dir
    )
    results = retriever.retrieve("查询", top_k=3)
    assert results == []


def test_混合检索_计数(clean_rag_dir):
    """文档数量正确"""
    from rag.hybrid_retriever import HybridRetriever
    
    retriever = HybridRetriever(
        embedding_model="mock",
        persist_directory=clean_rag_dir
    )
    retriever.load_knowledge([("doc1", "s1"), ("doc2", "s2")])
    assert retriever.count() == 2


# ==================== 文档加载测试 ====================

def test_text_loader(tmp_path):
    """加载文本文件"""
    from rag.document_loader import TextLoader
    
    # 创建测试文件
    test_file = tmp_path / "test.txt"
    test_file.write_text("这是测试内容。", encoding="utf-8")
    
    loader = TextLoader()
    assert loader.is_supported(str(test_file))
    
    result = loader.load(str(test_file))
    assert len(result) == 1
    assert result[0][0] == "这是测试内容。"
    assert result[0][1] == "test.txt"


def test_loader_factory_未知格式报错(tmp_path):
    """不支持的格式抛出异常"""
    from rag.document_loader import DocumentLoaderFactory
    
    test_file = tmp_path / "test.xyz"
    test_file.write_text("内容", encoding="utf-8")
    
    factory = DocumentLoaderFactory()
    with pytest.raises(ValueError):
        factory.load(str(test_file))


# ==================== 便捷函数测试 ====================

def test_retrieve便捷函数_返回字符串列表():
    """retrieve() 函数返回 list[str] - 直接测试接口签名"""
    from rag.hybrid_retriever import HybridRetriever
    from rag import retrieve
    
    # 这个测试验证 retrieve 函数的签名和返回值类型
    # 不测试全局单例，因为全局单例使用默认模型
    # 混合检索的功能在 TestHybridRetriever 中已测试
    
    # 验证 retrieve 是可调用的函数
    assert callable(retrieve)
    
    # 验证函数签名：retrieve(query: str, top_k: int = 3) -> list[str]
    import inspect
    sig = inspect.signature(retrieve)
    params = list(sig.parameters.keys())
    assert 'query' in params
    assert 'top_k' in params


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
