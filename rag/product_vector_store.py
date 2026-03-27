"""
商品向量库 - 基于 FAISS 的向量检索

功能：
1. 从 txt 文件构建商品知识库
2. 语义切块 + Embedding 向量化
3. FAISS 向量索引
4. 支持按平台隔离（每个平台独立的向量库文件）

txt 格式示例：
产品ID: P001
名称: 智能手表
分类: 电子产品
描述: 这是一款高性能智能手表，支持心率监测...

---
产品ID: P002
名称: 无线耳机
分类: 电子产品
描述: ...
"""

import os
import re
from typing import List, Dict, Optional
from pathlib import Path

import faiss
import numpy as np

from .chunker import SemanticChunker
from .embedding import SentenceEmbeddingFunction


class ProductVectorStore:
    """商品向量库
    
    基于 FAISS 的向量检索系统，专门用于商品知识的存储和检索。
    
    Attributes:
        platform: 平台名称（用于隔离不同平台的向量库）
        embedding_model: Embedding 模型名称
        chunker: 语义切块器
        index: FAISS 索引
        chunks: 原始块数据
        
    Example:
        store = ProductVectorStore("electronics")
        store.build_from_txt("products.txt")
        results = store.search("智能手表", top_k=5)
    """
    
    def __init__(
        self,
        platform: str,
        embedding_model: str = "BAAI/bge-small-zh-v1.5"
    ):
        """
        初始化商品向量库
        
        Args:
            platform: 平台名称
            embedding_model: Embedding 模型名称
        """
        self.platform = platform
        self.embedding_model = embedding_model
        self.chunker = SemanticChunker(
            min_chars=100,
            max_chars=500,
            overlap_chars=50
        )
        self.embedding_fn = SentenceEmbeddingFunction(embedding_model)
        self.index: Optional[faiss.Index] = None
        self.chunks: List[Dict] = []  # 原始块数据，包含 metadata
        self._embedding_dim: int = self.embedding_fn.dim
    
    @property
    def embedding_dim(self) -> int:
        """向量维度"""
        return self._embedding_dim
    
    def build_from_txt(self, txt_path: str) -> int:
        """
        从 txt 文件构建向量库
        
        txt 格式：
        产品ID: P001
        名称: 智能手表
        分类: 电子产品
        描述: 这是一款高性能智能手表...
        
        ---
        产品ID: P002
        ...
        
        Args:
            txt_path: txt 文件路径
            
        Returns:
            构建的块数量
        """
        # 1. 读取 txt
        with open(txt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 2. 按 --- 分隔解析产品
        product_texts = self._parse_products(content)
        
        # 3. 每个产品做语义切块
        all_chunks = []
        for product_info in product_texts:
            product_id = product_info.get("product_id", "")
            name = product_info.get("name", "")
            category = product_info.get("category", "")
            description = product_info.get("description", "")
            
            # 组合文本用于切分
            # 优先使用完整的产品信息作为文本
            full_text = f"{name}。{description}" if name else description
            
            if not full_text or not full_text.strip():
                continue
            
            # 切块时保留产品元信息
            chunk_metadata = {
                "product_id": product_id,
                "name": name,
                "category": category,
            }
            
            chunks = self.chunker.chunk(full_text, chunk_metadata)
            all_chunks.extend(chunks)
        
        # 4. 如果已有索引，先清空
        if self.index is not None:
            del self.index
        self.chunks = []
        
        # 5. 初始化 FAISS 索引
        self.index = faiss.IndexFlatIP(self._embedding_dim)  # 内积，用于余弦相似度
        
        # 6. 向量化并存入 FAISS
        texts = [chunk["content"] for chunk in all_chunks]
        if not texts:
            return 0
        
        # 批量向量化
        embeddings = self.embedding_fn.encode(texts)
        
        # 归一化（SentenceEmbeddingFunction 已归一化，但保险起见）
        if isinstance(embeddings, list):
            embeddings = np.array(embeddings)
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        embeddings = embeddings / norms
        
        # 添加到 FAISS 索引
        self.index.add(embeddings.astype('float32'))
        
        # 保存原始块数据
        self.chunks = all_chunks
        
        return len(all_chunks)
    
    def _parse_products(self, content: str) -> List[Dict]:
        """
        解析 txt 内容为产品列表
        
        Args:
            content: txt 文件内容
            
        Returns:
            产品信息列表
        """
        # 按 --- 分隔
        product_blocks = content.split('---')
        
        products = []
        for block in product_blocks:
            block = block.strip()
            if not block:
                continue
            
            product_info = self._parse_product_block(block)
            if product_info:
                products.append(product_info)
        
        return products
    
    def _parse_product_block(self, block: str) -> Optional[Dict]:
        """
        解析单个产品块
        
        支持的格式：
        产品ID: P001
        名称: 智能手表
        分类: 电子产品
        描述: ...
        
        Args:
            block: 产品块文本
            
        Returns:
            产品信息字典
        """
        product_info = {}
        
        # 提取产品ID
        match = re.search(r'产品ID[:：]\s*(.+)', block)
        if match:
            product_info["product_id"] = match.group(1).strip()
        
        # 提取名称
        match = re.search(r'名称[:：]\s*(.+)', block)
        if match:
            product_info["name"] = match.group(1).strip()
        
        # 提取分类
        match = re.search(r'分类[:：]\s*(.+)', block)
        if match:
            product_info["category"] = match.group(1).strip()
        
        # 提取描述（从"描述:"到块结尾）
        match = re.search(r'描述[:：]\s*(.+)', block, re.DOTALL)
        if match:
            product_info["description"] = match.group(1).strip()
        
        return product_info if product_info else None
    
    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        检索最相关的 top_k 个块
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            检索结果列表，每项包含 content 和 metadata
        """
        if self.index is None or self.index.ntotal == 0:
            return []
        
        # 限制 top_k 不超过总数
        top_k = min(top_k, self.index.ntotal)
        
        # 1. 将查询文本向量化
        query_embedding = self.embedding_fn.embed_text(query)
        query_vector = np.array([query_embedding]).astype('float32')
        
        # 归一化
        query_vector = query_vector / np.linalg.norm(query_vector, axis=1, keepdims=True)
        
        # 2. FAISS 搜索
        distances, indices = self.index.search(query_vector, top_k)
        
        # 3. 构建结果
        results = []
        for i, idx in enumerate(indices[0]):
            if idx >= 0 and idx < len(self.chunks):
                result = {
                    "content": self.chunks[idx]["content"],
                    "metadata": self.chunks[idx]["metadata"].copy(),
                    "score": float(distances[0][i])
                }
                results.append(result)
        
        return results
    
    def save(self, persist_dir: Optional[str] = None) -> str:
        """
        保存向量库到磁盘
        
        Args:
            persist_dir: 持久化目录，默认使用 ./data/{platform}
            
        Returns:
            保存路径
        """
        if persist_dir is None:
            persist_dir = f"./data/{self.platform}"
        
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        
        # 保存 FAISS 索引
        index_path = os.path.join(persist_dir, f"{self.platform}.index")
        if self.index is not None:
            faiss.write_index(self.index, index_path)
        
        # 保存 chunks 元数据
        import json
        chunks_path = os.path.join(persist_dir, f"{self.platform}_chunks.json")
        with open(chunks_path, 'w', encoding='utf-8') as f:
            json.dump(self.chunks, f, ensure_ascii=False, indent=2)
        
        return persist_dir
    
    def load(self, persist_dir: Optional[str] = None) -> bool:
        """
        从磁盘加载向量库
        
        Args:
            persist_dir: 持久化目录，默认使用 ./data/{platform}
            
        Returns:
            是否加载成功
        """
        if persist_dir is None:
            persist_dir = f"./data/{self.platform}"
        
        index_path = os.path.join(persist_dir, f"{self.platform}.index")
        chunks_path = os.path.join(persist_dir, f"{self.platform}_chunks.json")
        
        if not os.path.exists(index_path) or not os.path.exists(chunks_path):
            return False
        
        # 加载 FAISS 索引
        self.index = faiss.read_index(index_path)
        
        # 加载 chunks 元数据
        import json
        with open(chunks_path, 'r', encoding='utf-8') as f:
            self.chunks = json.load(f)
        
        return True
    
    def count(self) -> int:
        """返回块数量"""
        return len(self.chunks) if self.chunks else 0
