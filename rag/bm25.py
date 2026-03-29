"""
BM25 全文检索器

BM25 (Best Matching 25) 是一种经典的文本检索算法，
广泛应用于搜索引擎和文档检索系统。

与向量检索的对比：
- 向量检索：擅长语义相似度匹配（如"小狗"匹配"宠物"）
- BM25：擅长精确关键词匹配（如"iPhone 15"精确匹配）

BM25 算法核心公式：
score(D, Q) = Σ IDF(qi) × (tf(qi, D) × (k1 + 1)) / (tf(qi, D) + k1 × (1 - b + b × |D|/avgdl))

参数说明：
- k1: 词频饱和参数（默认1.5），控制词频增长对分数的影响
- b: 文档长度归一化参数（默认0.75），控制文档长度对分数的影响
- IDF: 逆文档频率，衡量词项的区分能力
"""

import math
from collections import Counter
from typing import List, Tuple
import re


class BM25:
    """
    BM25 检索器实现

    提供 BM25 算法的核心功能：
    - 添加文档
    - 查询文档
    - 计算 IDF 值

    使用示例：
        bm25 = BM25()
        bm25.add_documents(["文档1内容", "文档2内容", ...])
        results = bm25.search("查询词", top_k=10)
        # 返回: [(doc_id, score, content), ...]
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75, avg_doc_len: int = 500):
        """
        初始化 BM25 检索器

        Args:
            k1: 词频饱和参数
                - 值越小，词频增长对分数的影响越小
                - 典型值：1.2 ~ 2.0
            b: 文档长度归一化参数
                - b=1 表示完全按文档长度归一化
                - b=0 表示不考虑文档长度
                - 典型值：0.5 ~ 0.75
            avg_doc_len: 平均文档长度（词数）
        """
        self.k1 = k1
        self.b = b
        self.avg_doc_len = avg_doc_len
        self.documents: List[str] = []  # 文档列表
        self.doc_lengths: List[int] = []  # 各文档长度（词数）
        self.doc_freqs: Counter = Counter()  # 词项文档频率
        self.total_docs = 0  # 总文档数
        self._initialized = False  # 是否已初始化

    def _tokenize(self, text: str) -> List[str]:
        """
        分词（支持中文和英文）

        步骤：
        1. 使用jieba分词（支持中文）
        2. 转小写
        3. 过滤单字符词

        Args:
            text: 输入文本

        Returns:
            词汇列表
        """
        import jieba

        # 使用jieba分词（精确模式）
        words = jieba.cut(text, cut_all=False)

        # 转小写并过滤单字符
        result = []
        for w in words:
            w_lower = w.lower().strip()
            if len(w_lower) > 1:  # 过滤单字符
                result.append(w_lower)

        return result

    def add_documents(self, documents: List[str]):
        """
        添加文档到索引

        构建倒排索引，计算：
        - 各文档长度
        - 各词项的文档频率

        Args:
            documents: 文档内容列表
        """
        for doc in documents:
            # 分词
            tokens = self._tokenize(doc)
            # 保存文档
            self.documents.append(doc)
            # 保存文档长度
            self.doc_lengths.append(len(tokens))

            # 更新词项文档频率
            for token in set(tokens):
                self.doc_freqs[token] += 1

        self.total_docs = len(self.documents)
        self._initialized = True

    def search(self, query: str, top_k: int = 10) -> List[Tuple[int, float, str]]:
        """
        BM25 搜索

        计算查询词与所有文档的 BM25 分数，返回 top_k 个最相关文档。

        Args:
            query: 查询文本
            top_k: 返回结果数量

        Returns:
            List[(doc_id, score, content)]
            - doc_id: 文档索引
            - score: BM25 分数（越高越相关）
            - content: 文档内容
        """
        if not self._initialized or not self.documents:
            return []

        # 分词查询词
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        # 计算每个文档的分数
        doc_scores = []
        for doc_id, doc in enumerate(self.documents):
            score = self._calculate_score(doc, query_tokens, doc_id)
            doc_scores.append((doc_id, score, doc))

        # 按分数降序排序
        doc_scores.sort(key=lambda x: x[1], reverse=True)

        return doc_scores[:top_k]

    def _calculate_score(self, doc: str, query_tokens: List[str], doc_id: int) -> float:
        """
        计算单文档的 BM25 分数

        BM25 公式：
        score = Σ IDF(qi) × (tf(qi,D) × (k1+1)) / (tf(qi,D) + k1×(1-b+b×|D|/avgdl))

        Args:
            doc: 文档内容
            query_tokens: 查询词列表（已分词）
            doc_id: 文档索引

        Returns:
            BM25 分数
        """
        # 分词文档
        doc_tokens = self._tokenize(doc)
        doc_len = self.doc_lengths[doc_id]

        score = 0.0

        for token in query_tokens:
            # 如果词项不在索引中，跳过
            if token not in self.doc_freqs:
                continue

            # 文档频率
            doc_freq = self.doc_freqs[token]

            # IDF：逆文档频率
            # 公式：log((N - df + 0.5) / (df + 0.5) + 1)
            # 含义：在多少文档中出现越多，IDF 越低（区分度越低）
            idf = math.log((self.total_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1)

            # 词频 TF
            tf = doc_tokens.count(token)

            # BM25 分子：(tf × (k1 + 1))
            numerator = tf * (self.k1 + 1)

            # BM25 分母：tf + k1 × (1 - b + b × d/avgdl)
            denominator = tf + self.k1 * (
                1 - self.b + self.b * doc_len / self.avg_doc_len
            )

            score += idf * numerator / denominator

        return score

    def clear(self):
        """清空索引"""
        self.documents.clear()
        self.doc_lengths.clear()
        self.doc_freqs.clear()
        self.total_docs = 0
        self._initialized = False

    def count(self) -> int:
        """返回索引中的文档数量"""
        return len(self.documents)


class BM25Retriever:
    """
    BM25 检索器包装类

    封装 BM25，提供更友好的接口：
    - 输入：(content, source) 元组
    - 输出：(content, score, source) 元组

    使用示例：
        retriever = BM25Retriever()
        retriever.add_documents([
            ("文档1内容", "来源1"),
            ("文档2内容", "来源2")
        ])
        results = retriever.search("查询", top_k=5)
        # 返回: [("文档内容", 分数, "来源"), ...]
    """

    def __init__(self):
        """初始化包装类"""
        self.bm25 = BM25()
        self._doc_sources: List[str] = []  # 保存文档来源

    def add_documents(self, documents: List[Tuple[str, str]]):
        """
        添加文档

        Args:
            documents: 文档列表 List[(content, source)]
                - content: 文档文本内容
                - source: 文档来源标识
        """
        # 保存来源
        self._doc_sources = [src for _, src in documents]
        # 提取内容
        contents = [content for content, _ in documents]
        # 添加到 BM25 索引
        self.bm25.add_documents(contents)

    def search(self, query: str, top_k: int = 5) -> List[Tuple[str, float, str]]:
        """
        搜索文档

        Args:
            query: 查询文本
            top_k: 返回结果数量

        Returns:
            List[(content, score, source)]
            - content: 文档内容
            - score: BM25 分数
            - source: 文档来源
        """
        results = self.bm25.search(query, top_k)
        # 转换格式，添加来源
        return [
            (content, score, self._doc_sources[doc_id])
            for doc_id, score, content in results
        ]

    def count(self) -> int:
        """返回文档数量"""
        return self.bm25.count()
