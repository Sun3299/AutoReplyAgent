"""
RAG模块 - 知识检索增强生成

对外接口：
- rag.retrieve(query: str, top_k: int = 3) -> list[str]
- get_retriever() -> HybridRetriever
- load_document(file_path) -> List[tuple]
- load_documents(directory) -> List[tuple]
"""

from .hybrid_retriever import (
    HybridRetriever,
    get_retriever,
    retrieve,
    RetrievalItem
)
from .models import Document, RetrievalResult
from .advanced_chunker import HierarchicalChunker, TextChunk, chunk_text, chunk_documents
from .document_loader import (
    DocumentLoaderFactory,
    TextLoader,
    PDFLoader,
    DocxLoader,
    HtmlLoader,
    load_document,
    load_documents
)
from .embedding import SentenceEmbeddingFunction, MockEmbeddingFunction, create_embedding_function

__all__ = [
    # 核心检索
    "HybridRetriever",
    "get_retriever",
    "retrieve",
    "RetrievalItem",
    
    # 数据模型
    "Document",
    "RetrievalResult",
    
    # 分块器
    "HierarchicalChunker",
    "TextChunk",
    "chunk_text",
    "chunk_documents",
    
    # 文档加载
    "DocumentLoaderFactory",
    "TextLoader",
    "PDFLoader",
    "DocxLoader",
    "HtmlLoader",
    "load_document",
    "load_documents",
    
    # Embedding
    "SentenceEmbeddingFunction",
    "MockEmbeddingFunction",
    "create_embedding_function",
]