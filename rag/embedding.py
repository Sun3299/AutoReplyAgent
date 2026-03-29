"""
Embedding 函数 - 基于 transformers 本地加载

Embedding（文本向量化）是将文本转换为密集向量表示的过程。
在 RAG 系统中，Embedding 用于：
1. 将文档分块转换为向量，存储到向量数据库
2. 将用户查询转换为向量，用于相似度检索

支持的模型：
- BAAI/bge-small-zh-v1.5 (中文, 512维) ← 当前使用
- 本地路径：./models/bge-small-zh-v1.5

Embedding 模型选择要点：
- 维度：维度越高表示能力越强，但存储和检索更慢
- 中文支持：确保模型支持中文，否则中文文本会得到错误向量
- 归一化：输出向量应该 L2 归一化，用于余弦相似度计算
"""

import os
import numpy as np
from typing import List, Optional, Union


class LocalEmbedding:
    """
    本地 transformers BERT Embedding 实现

    使用 Hugging Face transformers 库加载本地 BERT 模型，
    将文本转换为固定维度的密集向量。

    模型加载策略：
    1. 使用 BertTokenizer 分词
    2. 使用 BertModel 编码
    3. 取 [CLS] token 的输出作为句子表示
    4. L2 归一化用于余弦相似度

    Attributes:
        model_path: 模型路径
        device: 计算设备 (cpu/cuda)
        dim: 向量维度
        tokenizer: 分词器
        model: BERT 模型

    使用示例：
        emb = LocalEmbedding("./models/bge-small-zh-v1.5")
        vector = emb.embed_text("这是一个测试句子")
        # vector.shape = (512,)
    """

    def __init__(self, model_path: str, device: str = "cpu"):
        """
        初始化本地 Embedding 模型

        Args:
            model_path: 模型文件路径（包含 config.json, tokenizer.json 等）
            device: 计算设备，"cpu" 或 "cuda"
        """
        from transformers import BertTokenizer, BertModel
        import torch

        self.model_path = model_path
        self.device = torch.device(device)

        print(f"加载本地模型: {model_path}")

        # 加载分词器和模型
        self.tokenizer = BertTokenizer.from_pretrained(
            model_path, local_files_only=True
        )
        self.model = BertModel.from_pretrained(model_path, local_files_only=True)
        self.model.eval()  # 评估模式
        self.model.to(self.device)  # 移动到指定设备

        # 获取模型维度
        self.dim = self.model.config.hidden_size
        print(f"模型加载完成, dimension={self.dim}")

    def embed_text(self, text: str) -> np.ndarray:
        """
        单条文本转向量

        步骤：
        1. 分词 (tokenize)
        2. 转换为 tensor
        3. BERT 编码
        4. 提取 [CLS] token 向量
        5. L2 归一化

        Args:
            text: 输入文本

        Returns:
            np.ndarray: 归一化向量，shape = (dim,)
        """
        import torch

        # 分词
        inputs = self.tokenizer(text, return_tensors="pt")
        # 移动到设备
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        # BERT 编码
        with torch.no_grad():
            outputs = self.model(**inputs)
            # 取 [CLS] token 的输出 (batch_size, seq_len, hidden_size)
            embedding = outputs.last_hidden_state[:, 0, :].cpu().numpy()

        # L2 归一化：使向量长度为 1，用于余弦相似度
        embedding = embedding / np.linalg.norm(embedding, axis=1, keepdims=True)
        return embedding[0]

    def embed_batch(self, texts: List[str], batch_size: int = 32) -> List[np.ndarray]:
        """
        批量文本转向量

        Args:
            texts: 文本列表
            batch_size: 批处理大小

        Returns:
            List[np.ndarray]: 向量列表
        """
        import torch

        all_embeddings = []

        # 分批处理
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]

            # 分词
            inputs = self.tokenizer(
                batch,
                return_tensors="pt",
                padding=True,  # 填充到同一长度
                truncation=True,  # 截断超长文本
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            # BERT 编码
            with torch.no_grad():
                outputs = self.model(**inputs)
                # 提取 [CLS] token
                embeddings = outputs.last_hidden_state[:, 0, :].cpu().numpy()

            # L2 归一化
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1, norms)  # 避免除零
            embeddings = embeddings / norms

            all_embeddings.extend(embeddings)

        return all_embeddings

    def encode(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """
        批量编码，返回 numpy 数组

        与 embed_batch 的区别：
        - embed_batch: 返回 List[np.ndarray]
        - encode: 返回 np.ndarray shape = (n, dim)

        Args:
            texts: 文本列表
            batch_size: 批处理大小

        Returns:
            np.ndarray: shape = (len(texts), dim)
        """
        return np.array(self.embed_batch(texts, batch_size))


class MockEmbeddingFunction:
    """
    Mock Embedding - 用于测试

    生成随机向量，确保：
    1. 相同文本产生相同向量（确定性）
    2. 向量已归一化

    用于在没有模型的情况下测试 RAG 流程。

    注意：随机向量没有语义意义，仅用于测试。
    """

    def __init__(self, dim: int = 768):
        """
        Args:
            dim: 向量维度
        """
        self.dim = dim

    def embed_text(self, text: str) -> np.ndarray:
        """
        生成随机向量

        使用文本的 hash 作为随机种子，确保相同文本产生相同向量。
        """
        np.random.seed(hash(text) % (2**32))
        emb = np.random.randn(self.dim)
        return emb / np.linalg.norm(emb)

    def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        """批量生成"""
        return [self.embed_text(t) for t in texts]

    def encode(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """批量编码"""
        return np.array(self.embed_batch(texts, batch_size))


class SentenceEmbeddingFunction:
    """
    统一的 Embedding 接口

    自动检测并加载本地模型或使用 Mock。
    提供统一的 embed_text/embed_batch/encode 接口。

    模型搜索路径（按优先级）：
    1. 指定的 local_model_path
    2. ./models/{model_name}
    3. ./models/{model_name_without_org}

    Attributes:
        model_name: 模型名称
        dim: 向量维度
        local_model_path: 本地模型路径（如果找到）
    """

    # 支持的预训练模型配置
    SUPPORTED_MODELS = {
        "all-MiniLM-L6-v2": {"dim": 384},  # 英文，轻量
        "all-mpnet-base-v2": {"dim": 768},  # 英文，高精度
        "paraphrase-multilingual-MiniLM-L12-v2": {"dim": 384},  # 多语言
        "text2vec-base-multilingual": {"dim": 768},  # 多语言中文
        "BAAI/bge-small-zh-v1.5": {"dim": 512},  # 中文
    }

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        device: str = "cpu",
        local_model_path: Optional[str] = None,
    ):
        """
        初始化 Embedding 函数（懒加载）

        注意：模型不会在此初始化，只有在首次调用 embed_text/embed_batch/encode 时才加载。

        Args:
            model_name: 模型名称
            device: 计算设备
            local_model_path: 本地模型路径（优先使用）
        """
        self.model_name = model_name
        self.device = device
        self.local_model_path = local_model_path or self._find_local_path()
        self._impl = None  # type: Optional[LocalEmbedding | MockEmbeddingFunction]
        self._loaded = False

        # 预计算维度（不加载模型）
        if model_name == "mock":
            mock_fn = MockEmbeddingFunction()
            self._dim = mock_fn.dim
        elif self.local_model_path and os.path.exists(self.local_model_path):
            # 从模型配置获取维度，不实际加载模型
            self._dim = self._get_dim_from_config()
        else:
            raise ValueError(f"无法加载模型 {model_name}，本地路径不存在")

    def _find_local_path(self) -> Optional[str]:
        """
        查找本地模型路径

        搜索顺序：
        1. 模型名称作为路径
        2. ./models/{org}--{name}
        3. ./models/{name}
        """
        candidates = [
            self.model_name,
            f"./models/{self.model_name.replace('/', '--')}",
            f"./models/{self.model_name.split('/')[-1]}",
        ]
        for path in candidates:
            if os.path.exists(path):
                config_file = os.path.join(path, "config.json")
                if os.path.exists(config_file):
                    return path
        return None

    @property
    def dim(self) -> int:
        """向量维度"""
        return self._dim

    def _get_dim_from_config(self) -> int:
        """从模型配置读取维度，不加载模型"""
        import json

        config_path = os.path.join(self.local_model_path, "config.json")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                return config.get("hidden_size", 512)
        return 512

    def _ensure_loaded(self):
        """确保模型已加载（懒加载）"""
        if self._loaded:
            return
        if self.model_name == "mock":
            self._impl = MockEmbeddingFunction()
        else:
            self._impl = LocalEmbedding(self.local_model_path, self.device)
        self._loaded = True

    def embed_text(self, text: str):
        """单条文本转向量"""
        self._ensure_loaded()
        return self._impl.embed_text(text)

    def embed_batch(self, texts: List[str], batch_size: int = 32):
        """批量文本转向量"""
        self._ensure_loaded()
        return self._impl.embed_batch(texts, batch_size)

    def encode(self, texts: List[str], batch_size: int = 32):
        """批量编码为数组"""
        self._ensure_loaded()
        return self._impl.encode(texts, batch_size)


def create_embedding_function(
    model_name: str = "all-MiniLM-L6-v2", device: str = "cpu"
):
    """
    工厂函数：创建 Embedding 函数

    便捷接口，自动选择合适的实现。

    Args:
        model_name: 模型名称或 "mock"
        device: 计算设备

    Returns:
        Embedding 函数对象
    """
    if model_name == "mock":
        return MockEmbeddingFunction()
    return SentenceEmbeddingFunction(model_name, device)
