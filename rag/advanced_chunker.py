"""
高级文本分块器 - 三层分块策略

分块是 RAG 系统中的关键步骤，决定了检索的精度。

三层分块策略：
1. 结构分块 (StructuralChunker) - 按自然边界切分
   - Markdown/HTML 标题
   - 段落 <p>
   - 列表项 <li>
   - 表格行 <tr>

2. 语义分块 (SemanticChunker) - 合并相关内容
   - 基于词汇重叠度（Jaccard相似度）
   - 避免在语义连贯的内容中间切断

3. 大小分块 (SizeChunker) - 控制块大小
   - 确保每个块在 [min, max] 范围内
   - 按句子边界切分大块文本
"""

import re
from typing import List, Tuple, Optional
from dataclasses import dataclass, field


@dataclass
class TextChunk:
    """
    文本块数据模型

    表示分块后的一个文本片段，包含其位置信息和元数据。

    Attributes:
        content: 文本内容
        source: 来源（如文件名、URL）
        chunk_index: 块在文档中的顺序索引
        parent_chunk: 父块索引（用于跟踪分割关系）
        metadata: 扩展元数据
    """

    content: str  # 文本内容
    source: str  # 来源标识
    chunk_index: int = 0  # 块索引
    parent_chunk: Optional[int] = None  # 父块索引（分割时设置）
    metadata: dict = field(default_factory=dict)  # 元数据

    def __post_init__(self):
        """确保 metadata 不为 None"""
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "content": self.content,
            "source": self.source,
            "chunk_index": self.chunk_index,
            "parent_chunk": self.parent_chunk,
            "metadata": self.metadata,
        }


class StructuralChunker:
    """
    第一层：结构分块器

    按文档的自然结构边界切分文本，如标题、段落等。
    使用正则表达式匹配各种结构模式。

    支持的结构类型：
    - Markdown 标题 (# ## ### 等)
    - HTML 标题 (<h1> 到 <h6>)
    - 段落 (<p>)
    - 列表项 (<li>)
    - 表格行 (<tr>)
    - 长句（100+字符且以逗号分隔）
    """

    # 结构模式：正则表达式 + 类型名称
    STRUCTURE_PATTERNS = [
        (r"\n#{1,6}\s+[^\n]+", "heading"),  # Markdown 标题
        (r"<h[1-6][^>]*>.*?</h[1-6]>", "html_heading"),  # HTML 标题
        (r"<p[^>]*>.*?</p>", "paragraph"),  # 段落
        (r"<li[^>]*>.*?</li>", "list_item"),  # 列表项
        (r"<tr[^>]*>.*?</tr>", "table_row"),  # 表格行
        (r"[^。！？.!?\n]{100,}[,，]\s*", "clause"),  # 长句
    ]

    def __init__(self):
        """
        初始化结构分块器

        预编译所有正则表达式以提高性能
        """
        # 预编译正则：[(pattern对象, type名), ...]
        self.patterns = [(re.compile(p), t) for p, t in self.STRUCTURE_PATTERNS]

    def split_by_structure(self, text: str) -> List[Tuple[str, str, dict]]:
        """
        按结构分割文本

        遍历文本，找到第一个匹配的结构模式，切分并递归处理剩余部分。
        未匹配到结构的文本被标记为 'text' 类型。

        Args:
            text: 待分割的原始文本

        Returns:
            List[(content, structure_type, metadata)]
            - content: 片段内容
            - structure_type: 结构类型 ('heading', 'paragraph', 'text' 等)
            - metadata: 额外元数据（当前为空字典）
        """
        if not text:
            return []

        segments = []
        remaining = text

        # 循环处理，直到没有剩余文本
        while remaining:
            best_match = None
            best_pos = len(remaining)  # 记录最早匹配位置
            matched_type = "text"

            # 遍历所有模式，找最早匹配
            for pattern, seg_type in self.patterns:
                match = pattern.search(remaining)
                if match and match.start() < best_pos:
                    best_match = match
                    best_pos = match.start()
                    matched_type = seg_type

            if best_match:
                # 提取匹配前的文本作为普通文本段
                before = remaining[:best_pos].strip()
                if before:
                    segments.append((before, "text", {}))

                # 添加匹配到的结构化内容
                segments.append((best_match.group(), matched_type, {}))
                # 继续处理剩余部分
                remaining = remaining[best_match.end() :]
            else:
                # 没有匹配到任何结构，整个剩余文本作为普通文本
                if remaining.strip():
                    segments.append((remaining.strip(), "text", {}))
                break

        return segments


class SemanticChunker:
    """
    第二层：语义分块器

    基于词汇重叠度（Jaccard相似度）合并语义相关的片段。
    这确保了语义连贯的内容不会被分散到不同的块中。

    Jaccard 相似度 = |A ∩ B| / |A ∪ B|
    - A、B 为两个文本的词汇集合
    - 阈值默认 0.3，即重叠 > 30% 时合并
    """

    def __init__(self, similarity_threshold: float = 0.3):
        """
        初始化语义分块器

        Args:
            similarity_threshold: Jaccard 相似度阈值
                               低于此值的两段文本不合并
        """
        self.similarity_threshold = similarity_threshold

    def should_merge(self, chunk1: str, chunk2: str) -> bool:
        """
        判断两个片段是否应该合并

        计算两个文本的词汇集合的 Jaccard 相似度，
        如果超过阈值则返回 True（应该合并）。

        Args:
            chunk1: 第一个文本片段
            chunk2: 第二个文本片段

        Returns:
            bool: 如果相似度超过阈值则返回 True
        """
        # 提取两段文本的词汇集合
        words1 = set(self._extract_words(chunk1))
        words2 = set(self._extract_words(chunk2))

        # 空集合不合并
        if not words1 or not words2:
            return False

        # 计算 Jaccard 相似度
        overlap = len(words1 & words2)  # 交集大小
        union = len(words1 | words2)  # 并集大小
        jaccard = overlap / union if union > 0 else 0

        return jaccard > self.similarity_threshold

    def _extract_words(self, text: str) -> List[str]:
        """
        从文本中提取词汇（支持中文和英文）

        步骤：
        1. 使用jieba分词（支持中文）
        2. 转小写
        3. 过滤掉单字符的词

        Args:
            text: 输入文本

        Returns:
            词汇列表
        """
        import jieba

        # 使用jieba分词（精确模式）
        words = jieba.cut(text, cut_all=False)

        # 转小写并过滤
        result = []
        for w in words:
            w_lower = w.lower().strip()
            # 过滤单字符和纯空白
            if len(w_lower) > 1:
                result.append(w_lower)

        return result

    def merge_segments(self, segments: List[Tuple[str, str, dict]]) -> List[TextChunk]:
        """
        合并语义相关的片段

        遍历结构分块产生的片段，相邻片段如果语义相关则合并。

        Args:
            segments: 结构分块结果 List[(content, type, metadata)]

        Returns:
            List[TextChunk]: 合并后的文本块列表
        """
        if not segments:
            return []

        chunks = []
        # 初始化第一个片段
        current_content = segments[0][0]
        current_type = segments[0][1]
        chunk_index = 0

        # 遍历剩余片段
        for i in range(1, len(segments)):
            content, seg_type, meta = segments[i]

            # 检查是否应该与当前块合并
            if self.should_merge(current_content, content):
                # 合并：用换行符连接
                current_content += "\n" + content
            else:
                # 不合并，保存当前块并开始新块
                if current_content.strip():
                    chunks.append(
                        TextChunk(
                            content=current_content.strip(),
                            source="merged",
                            chunk_index=chunk_index,
                            metadata={"primary_type": current_type},
                        )
                    )
                    chunk_index += 1

                current_content = content
                current_type = seg_type

        # 保存最后一块
        if current_content.strip():
            chunks.append(
                TextChunk(
                    content=current_content.strip(),
                    source="merged",
                    chunk_index=chunk_index,
                    metadata={"primary_type": current_type},
                )
            )

        return chunks


class SentenceChunker:
    """
    第二层：句子切分器

    将段落按句子边界切分成独立的句子，
    为后续语义合并提供更精准的粒度。
    """

    def split_by_sentences(self, text: str) -> List[TextChunk]:
        """
        按句子边界切分

        Args:
            text: 段落文本

        Returns:
            TextChunk列表，每个chunk是一个句子
        """
        if not text or not text.strip():
            return []

        # 按句子结束符分割，保留分隔符
        # r'([。！？.!?\n])' 会捕获分隔符
        parts = re.split(r"([。！？.!?\n])", text)

        chunks = []
        current = ""

        # parts格式: [文本, 分隔符, 文本, 分隔符, ...]
        for i in range(0, len(parts) - 1, 2):
            sentence = parts[i] + parts[i + 1]
            if sentence.strip():
                chunks.append(TextChunk(content=sentence.strip(), source=""))

        # 处理最后一段（如果没有分隔符）
        if len(parts) % 2 == 1 and parts[-1].strip():
            if chunks:
                # 合并到最后一块
                chunks[-1].content += parts[-1].strip()
            else:
                chunks.append(TextChunk(content=parts[-1].strip(), source=""))

        return chunks

    def merge_to_chunks(
        self, sentences: List[TextChunk], max_size: int = 800
    ) -> List[TextChunk]:
        """
        将句子合并成合适大小的块

        Args:
            sentences: 句子列表
            max_size: 最大块大小

        Returns:
            合并后的chunk列表
        """
        if not sentences:
            return []

        result = []
        current = ""
        current_source = ""

        for sent in sentences:
            if not current:
                current = sent.content
                current_source = sent.source
            elif len(current) + len(sent.content) <= max_size:
                current += sent.content
            else:
                result.append(TextChunk(content=current, source=current_source))
                current = sent.content
                current_source = sent.source

        if current:
            result.append(TextChunk(content=current, source=current_source))

        return result


class SizeChunker:
    """
    第三层：大小分块器

    确保每个文本块的大小在指定范围内 [min_chunk_size, max_chunk_size]。
    如果块过大，按句子边界切分成多个子块。

    切分策略：
    1. 按句子结束符（。！？.!?\n）分割
    2. 累积句子直到接近上限
    3. 如果单个句子就超过上限，强制按字符切分
    """

    def __init__(self, min_chunk_size: int = 100, max_chunk_size: int = 800):
        """
        初始化大小分块器

        Args:
            min_chunk_size: 最小块大小（字符数）
            max_chunk_size: 最大块大小（字符数）
        """
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size

    def split_by_size(self, chunks: List[TextChunk]) -> List[TextChunk]:
        """
        按大小分割过大的块

        Args:
            chunks: 待处理的文本块列表

        Returns:
            分割后的文本块列表
        """
        result = []
        global_index = 0  # 全局块索引

        for chunk in chunks:
            content = chunk.content

            # 大小合适，直接保留
            if len(content) <= self.max_chunk_size:
                chunk.chunk_index = global_index
                result.append(chunk)
                global_index += 1
                continue

            # 过大，需要分割
            sub_chunks = self._split_large_chunk(content)
            for i, sub_content in enumerate(sub_chunks):
                if sub_content.strip():
                    result.append(
                        TextChunk(
                            content=sub_content.strip(),
                            source=chunk.source,
                            chunk_index=global_index,
                            parent_chunk=chunk.chunk_index,
                            metadata={**chunk.metadata, "sub_chunk": i},
                        )
                    )
                    global_index += 1

        return result

    def _split_large_chunk(self, content: str) -> List[str]:
        """
        分割大块文本

        按句子边界切分，累积到接近 max_chunk_size 时开始新块。

        Args:
            content: 待分割的长文本

        Returns:
            分割后的文本片段列表
        """
        if len(content) <= self.max_chunk_size:
            return [content]

        sub_chunks = []

        # 按句子结束符分割，保留分隔符
        # r'([。！？.!?\n])' 会捕获分隔符
        sentences = re.split(r"([。！？.!?\n])", content)

        current = ""
        # sentences 格式：[文本, 分隔符, 文本, 分隔符, ...]
        # 我们按 (文本+分隔符) 配对处理
        for i in range(0, len(sentences) - 1, 2):
            # 句子 = 文本 + 分隔符
            sentence = sentences[i] + sentences[i + 1]

            # 检查加入这句是否会超过限制
            if len(current) + len(sentence) <= self.max_chunk_size:
                current += sentence
            else:
                # 超过限制，保存当前块
                if current:
                    sub_chunks.append(current)

                # 如果单个句子就超过限制，强制按字符切分
                if len(sentence) > self.max_chunk_size:
                    current = sentence
                else:
                    current = sentence

        # 保存最后一块
        if current:
            sub_chunks.append(current)

        # 如果分割失败（不应该发生），使用字符级分割
        if not sub_chunks and content:
            parts = []
            # 步长 = max - min，确保每块都在范围内
            step = self.max_chunk_size - self.min_chunk_size
            for i in range(0, len(content), step):
                parts.append(content[i : i + self.max_chunk_size])
            sub_chunks = parts

        return sub_chunks


class HierarchicalChunker:
    """
    四层分块器

    整合四层分块策略，按顺序执行：
    结构分块 → 句子切分 → 语义合并 → 大小分块

    Usage:
        chunker = HierarchicalChunker()
        chunks = chunker.chunk("长文本...", "source_file.txt")
        # 返回 List[TextChunk]
    """

    def __init__(
        self,
        min_chunk_size: int = 100,
        max_chunk_size: int = 800,
        semantic_threshold: float = 0.3,
    ):
        """
        初始化四层分块器

        Args:
            min_chunk_size: 最小块大小
            max_chunk_size: 最大块大小
            semantic_threshold: 语义合并阈值
        """
        # 初始化四个分块器
        self.structural_chunker = StructuralChunker()
        self.sentence_chunker = SentenceChunker()
        self.semantic_chunker = SemanticChunker(similarity_threshold=semantic_threshold)
        self.size_chunker = SizeChunker(min_chunk_size, max_chunk_size)

    def chunk(self, text: str, source: str = "unknown") -> List[TextChunk]:
        """
        执行四层分块

        完整流程：
        1. 结构分块：按自然边界切分
        2. 句子切分：按句子边界切分段落
        3. 语义合并：合并相似句子
        4. 大小分块：控制块大小
        5. 重新编号块索引

        Args:
            text: 原始文本
            source: 来源标识

        Returns:
            List[TextChunk]: 分块结果
        """
        # 第一层：结构分块
        structural_segments = self.structural_chunker.split_by_structure(text)

        # 处理空文本情况
        if not structural_segments:
            structural_segments = [(text, "text", {})]

        # 第二层：句子切分（把段落切成独立句子）
        all_sentences = []
        for segment_text, seg_type, meta in structural_segments:
            sentences = self.sentence_chunker.split_by_sentences(segment_text)
            all_sentences.extend(sentences)

        # 过滤空句子
        all_sentences = [s for s in all_sentences if s.content.strip()]

        # 第三层：语义合并（在句子级别合并）
        if all_sentences:
            # 转换为 (content, type, metadata) 格式供 semantic_chunker 使用
            seg_tuples = [(s.content, "sentence", {}) for s in all_sentences]
            semantic_chunks = self.semantic_chunker.merge_segments(seg_tuples)
        else:
            semantic_chunks = []

        # 处理语义合并后为空的情况
        if not semantic_chunks:
            stripped = text.strip()
            if stripped:
                semantic_chunks = [TextChunk(content=stripped, source=source)]
            else:
                semantic_chunks = []

        # 第四层：大小分块
        final_chunks = self.size_chunker.split_by_size(semantic_chunks)

        # 重新编号
        for i, chunk in enumerate(final_chunks):
            chunk.source = source
            chunk.chunk_index = i

        return final_chunks

    def chunk_documents(self, documents: List[Tuple[str, str]]) -> List[TextChunk]:
        """
        批量分块多个文档

        Args:
            documents: 文档列表 List[(content, source)]

        Returns:
            所有文档的分块列表
        """
        all_chunks = []
        for content, source in documents:
            chunks = self.chunk(content, source)
            all_chunks.extend(chunks)

        # 重新编号
        for i, chunk in enumerate(all_chunks):
            chunk.chunk_index = i

        return all_chunks


def chunk_text(text: str, source: str = "unknown") -> List[str]:
    """
    便捷函数：分块并返回纯内容列表

    简化接口，只返回文本内容，不包含元数据。

    Args:
        text: 原始文本
        source: 来源标识

    Returns:
        List[str]: 分块后的文本内容列表
    """
    chunker = HierarchicalChunker()
    chunks = chunker.chunk(text, source)
    return [c.content for c in chunks]


def chunk_documents(documents: List[Tuple[str, str]]) -> List[str]:
    """
    便捷函数：批量分块并返回纯内容列表

    Args:
        documents: 文档列表 List[(content, source)]

    Returns:
        所有分块的文本内容列表
    """
    chunker = HierarchicalChunker()
    chunks = chunker.chunk_documents(documents)
    return [c.content for c in chunks]
