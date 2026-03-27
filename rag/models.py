"""
RAG模块 - 数据模型定义

本文件定义 RAG 系统中使用的数据结构：
- Document: 文档片段，用于存储检索结果
- RetrievalResult: 检索结果，包含查询和文档列表
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Document:
    """
    文档片段数据模型
    
    Attributes:
        content: 文档内容文本
        source: 文档来源（如文件名、URL等）
        score: 相似度分数（检索时填充）
        metadata: 额外元数据（如标题、创建时间等）
    """
    content: str          # 文档的文本内容
    source: str          # 文档来源标识（文件名/URL/分类等）
    score: float = 0.0   # 检索时的相似度分数，默认为0
    metadata: Optional[dict] = None  # 扩展元数据，可存储任意信息
    
    def to_dict(self) -> dict:
        """
        转换为字典格式
        
        Returns:
            包含文档所有字段的字典
        """
        return {
            "content": self.content,
            "source": self.source,
            "score": self.score,
            "metadata": self.metadata or {}
        }


@dataclass
class RetrievalResult:
    """
    检索结果数据模型
    
    包含一次完整检索操作的所有信息：
    - 原始查询词
    - 检索到的文档列表
    - 总文档数
    
    Attributes:
        query: 用户输入的查询文本
        documents: 检索到的文档列表
        total: 符合条件的总文档数
    """
    query: str                      # 原始查询文本
    documents: list[Document]      # 检索到的文档列表
    total: int                    # 符合条件的最总文档数
    
    def to_dict(self) -> dict:
        """
        转换为字典格式
        
        Returns:
            包含检索结果所有字段的字典
        """
        return {
            "query": self.query,
            "documents": [d.to_dict() for d in self.documents],
            "total": self.total
        }
