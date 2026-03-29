"""
向量存储 - 基于 Chroma

Chroma 是一个开源的向量数据库，专门为 LLM 应用设计。
特点：
- 轻量级，易于部署
- 支持持久化存储
- 内置 HNSW 近似最近邻搜索
- 支持元数据过滤

本模块封装 Chroma，提供：
- 本地持久化存储
- 相似度搜索
- 元数据过滤

注意：Chroma 使用余弦相似度，embeddings 应该已经过 L2 归一化
"""

import numpy as np
from typing import List, Optional, Dict, Any
from pathlib import Path

import chromadb
from chromadb.config import Settings

from .models import Document


class ChromaVectorStore:
    """
    Chroma 向量存储封装类
    
    提供向量存储和检索功能，数据持久化到本地目录。
    
    Attributes:
        collection_name: 集合名称
        embedding_dim: 向量维度
    
    使用示例：
        store = ChromaVectorStore(
            persist_directory="./data",
            embedding_dim=512
        )
        store.add_documents(documents, embeddings)
        results = store.search(query_embedding, top_k=3)
    """
    
    def __init__(
        self,
        collection_name: str = "rag_collection",
        persist_directory: Optional[str] = None,
        embedding_dim: int = 384
    ):
        """
        初始化 Chroma 向量存储
        
        Args:
            collection_name: 集合名称，用于区分不同数据集
            persist_directory: 持久化目录，None 则使用内存存储
            embedding_dim: 向量维度，必须与 Embedding 模型输出一致
        """
        self.collection_name = collection_name
        self.embedding_dim = embedding_dim
        self._client: Optional[chromadb.Client] = None
        self._collection = None
        
        # 设置持久化目录
        if persist_directory:
            self._persist_directory = Path(persist_directory)
            self._persist_directory.mkdir(parents=True, exist_ok=True)
        else:
            self._persist_directory = None
    
    @property
    def client(self):
        """
        获取 Chroma 客户端
        
        根据是否设置持久化目录，返回：
        - 持久化客户端（PersistentClient）：数据保存在本地
        - 内存客户端（Client）：数据仅存在内存中
        """
        if self._client is None:
            if self._persist_directory:
                # 持久化客户端
                self._client = chromadb.PersistentClient(
                    path=str(self._persist_directory),
                    settings=Settings(anonymized_telemetry=False)  # 禁用遥测
                )
            else:
                # 内存客户端
                self._client = chromadb.Client()
        return self._client
    
    @property
    def collection(self):
        """
        获取 Chroma 集合
        
        集合是 Chroma 中组织数据的基本单位。
        如果集合不存在，则创建一个新集合。
        """
        if self._collection is None:
            try:
                # 尝试获取已存在的集合
                self._collection = self.client.get_collection(name=self.collection_name)
            except Exception:
                # 集合不存在，创建新集合
                self._collection = self.client.create_collection(
                    name=self.collection_name
                )
        return self._collection
    
    def add_documents(
        self,
        documents: List[Document],
        embeddings: List[np.ndarray],
        ids: Optional[List[str]] = None
    ):
        """
        添加文档和对应的向量
        
        Args:
            documents: Document 对象列表
            embeddings: 向量列表，与 documents 一一对应
            ids: 文档 ID 列表，默认自动生成
        """
        # 生成默认 ID
        if ids is None:
            ids = [f"doc_{i}" for i in range(len(documents))]
        
        # 转换 numpy array 为 list（Chroma 要求）
        embeddings_list = [
            emb.tolist() if isinstance(emb, np.ndarray) else emb
            for emb in embeddings
        ]
        
        # 构建元数据
        metadatas = []
        for doc in documents:
            meta = {"source": doc.source}  # 总是包含 source
            if doc.metadata:
                meta.update(doc.metadata)    # 合并额外元数据
            metadatas.append(meta)
        
        # 提取文本内容
        texts = [doc.content for doc in documents]
        
        # 添加到 Chroma 集合
        self.collection.add(
            embeddings=embeddings_list,
            documents=texts,
            metadatas=metadatas,
            ids=ids
        )
    
    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 3,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """
        向量相似度搜索
        
        使用余弦相似度在向量空间中查找最相似的文档。
        
        Args:
            query_embedding: 查询向量
            top_k: 返回结果数量
            filter_metadata: 元数据过滤条件
            
        Returns:
            List[Document]: 检索结果列表，按相似度降序排列
        """
        # 转换向量格式
        query_embedding = (
            query_embedding.tolist()
            if isinstance(query_embedding, np.ndarray)
            else query_embedding
        )
        
        # 执行查询
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filter_metadata  # 元数据过滤条件
        )
        
        # 解析结果
        documents = []
        if results and results['documents']:
            doc_list = results['documents'][0]
            metadatas = results.get('metadatas', [[]])[0]
            distances = results.get('distances', [[]])[0]
            
            for i, doc_content in enumerate(doc_list):
                # 获取元数据和距离
                meta = metadatas[i] if i < len(metadatas) else {}
                distance = distances[i] if i < len(distances) else 0.0
                
                # 获取来源
                source = meta.get("source", "unknown") if meta else "unknown"
                
                # 将距离转换为相似度分数
                # Chroma 返回的 distance 是 L2 距离（未归一化）
                # 由于我们的 embedding 已经过 L2 归一化，distance 范围是 [0, 2]
                # 转换为 [0, 1] 范围的相似度：1 - distance/2
                # 这样 0 距离（完全相同）→ 1.0 相似度
                # 2 距离（完全相反）→ 0.0 相似度
                normalized_distance = max(0.0, min(distance, 2.0)) / 2.0
                score = float(1.0 - normalized_distance)
                
                doc = Document(
                    content=doc_content,
                    source=source,
                    score=score,
                    metadata=meta
                )
                documents.append(doc)
        
        return documents
    
    def delete(self, ids: List[str]):
        """
        删除指定 ID 的文档
        
        Args:
            ids: 要删除的文档 ID 列表
        """
        self.collection.delete(ids=ids)
    
    def clear(self):
        """
        清空集合
        
        删除整个集合及其所有数据
        """
        try:
            self.client.delete_collection(name=self.collection_name)
            self._collection = None
        except Exception:
            pass
    
    def count(self) -> int:
        """返回集合中的文档数量"""
        return self.collection.count()


class VectorStore:
    """
    向量存储接口（兼容旧代码）
    
    封装 ChromaVectorStore，提供统一的接口。
    主要用于兼容之前的代码，新代码建议直接使用 ChromaVectorStore。
    
    使用示例：
        store = VectorStore(persist_directory="./data", embedding_dim=512)
        store.add_documents(docs, embeddings)
        results = store.search(query_emb, top_k=5)
    """
    
    def __init__(
        self,
        persist_directory: Optional[str] = None,
        embedding_dim: int = 384
    ):
        """
        初始化向量存储
        
        Args:
            persist_directory: 持久化目录
            embedding_dim: 向量维度
        """
        self._chroma = ChromaVectorStore(
            persist_directory=persist_directory,
            embedding_dim=embedding_dim
        )
    
    def add_documents(
        self,
        documents: List[Document],
        embeddings: List[np.ndarray]
    ):
        """添加文档"""
        self._chroma.add_documents(documents, embeddings)
    
    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 3,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """搜索相似文档"""
        return self._chroma.search(query_embedding, top_k, filter_metadata)
    
    def delete(self, ids: List[str]):
        """删除文档"""
        self._chroma.delete(ids)
    
    def clear(self):
        """清空数据"""
        self._chroma.clear()
    
    def count(self) -> int:
        """文档数量"""
        return self._chroma.count()
