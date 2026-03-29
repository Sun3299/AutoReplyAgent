"""
文本分块器 - 已废弃，请使用 rag.advanced_chunker.HierarchicalChunker

此文件保留用于参考，不建议在新代码中使用。
deprecated: 请使用 rag.advanced_chunker.HierarchicalChunker
"""

from typing import List


class TextChunker:
    """文本分块"""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_text(self, text: str) -> List[str]:
        """将文本分成块"""
        if not text:
            return []

        text = text.strip()
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size

            if end >= len(text):
                chunks.append(text[start:])
                break

            chunk = text[start:end]

            last_period = chunk.rfind("。")
            last_newline = chunk.rfind("\n")
            last_comma = chunk.rfind("，")

            split_pos = max(last_period, last_newline, last_comma)

            if split_pos > start + self.chunk_size // 2:
                chunk = text[start : split_pos + 1]
                start = split_pos + 1
            else:
                chunk = text[start:end]
                start = end - self.chunk_overlap

            if chunk.strip():
                chunks.append(chunk)

        return chunks

    def chunk_documents(self, texts: List[tuple]) -> List[tuple]:
        """处理多个文档 (text, source)"""
        result = []
        for text, source in texts:
            chunks = self.chunk_text(text)
            for chunk in chunks:
                result.append((chunk, source))
        return result
