"""
语义切块器 - 按句子切分，保持上下文重叠

语义切块规则：
- 按句子切分 (句号、问号、感叹号)
- 块大小: 100-500 characters
- 重叠: 50 characters (保持上下文)
- 支持结构化字段: product_id, name, category
"""

import re
from typing import List, Dict, Optional


class SemanticChunker:
    """语义切块器
    
    按句子切分文本，控制块大小在指定范围内，
    并通过重叠保持上下文连贯性。
    
    Attributes:
        min_chars: 最小块大小
        max_chars: 最大块大小
        overlap_chars: 重叠字符数
    """
    
    def __init__(self, min_chars: int = 100, max_chars: int = 500, overlap_chars: int = 50):
        """
        初始化语义切块器
        
        Args:
            min_chars: 最小块大小（字符数）
            max_chars: 最大块大小（字符数）
            overlap_chars: 块之间重叠的字符数
        """
        self.min_chars = min_chars
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars
    
    def chunk(self, text: str, metadata: Optional[Dict] = None) -> List[Dict]:
        """
        将文本切分成块
        
        切分策略：
        1. 按句子结束符（。！？.!?）分割成句子
        2. 累积句子直到接近 max_chars
        3. 如果单个句子超过 max_chars，强制按字符切分
        4. 块之间保留 overlap_chars 重叠
        
        Args:
            text: 待切分的文本
            metadata: 额外元数据，会传递给每个块
            
        Returns:
            List[{"content": "...", "metadata": {"product_id": "...", "start": 0, "end": 100}}]
        """
        if not text or not text.strip():
            return []
        
        # 句子分割正则：按中文和英文句子结束符分割
        # 保留分隔符以便恢复句子结构
        sentence_pattern = r'([。！？.!?])'
        parts = re.split(sentence_pattern, text)
        
        # 重新组合句子：文本 + 分隔符
        sentences = []
        for i in range(0, len(parts) - 1, 2):
            if i + 1 < len(parts):
                sentence = parts[i] + parts[i + 1]
            else:
                sentence = parts[i]
            if sentence.strip():
                sentences.append(sentence)
        
        # 处理最后一部分（如果没有分隔符）
        if len(parts) % 2 == 1 and parts[-1].strip():
            sentences.append(parts[-1])
        
        if not sentences:
            return []
        
        chunks = []
        current_chunk = ""
        current_start = 0
        
        for sentence in sentences:
            sentence_len = len(sentence)
            
            # 单个句子就超过 max_chars，强制分割
            if sentence_len > self.max_chars:
                # 保存当前块
                if current_chunk:
                    chunks.append(self._create_chunk(
                        current_chunk, current_start, metadata
                    ))
                    current_chunk = ""
                
                # 强制按字符切割这个超长句子
                sub_chunks = self._split_long_sentence(
                    sentence, current_start, metadata
                )
                chunks.extend(sub_chunks)
                current_start = current_start + len(current_chunk) + len(sentence)
                continue
            
            # 加入句子后超过 max_chars
            if len(current_chunk) + sentence_len > self.max_chars:
                # 保存当前块（如果不为空）
                if current_chunk:
                    chunks.append(self._create_chunk(
                        current_chunk, current_start, metadata
                    ))
                    
                    # 重叠：保留最后 overlap_chars 个字符作为新块的开头
                    overlap_text = current_chunk[-self.overlap_chars:] if self.overlap_chars > 0 else ""
                    current_start = current_start + len(current_chunk) - len(overlap_text)
                    current_chunk = overlap_text
                else:
                    current_start = current_start + len(current_chunk)
            
            current_chunk += sentence
        
        # 处理最后一块
        if current_chunk and len(current_chunk) >= self.min_chars:
            chunks.append(self._create_chunk(current_chunk, current_start, metadata))
        elif current_chunk and len(current_chunk) < self.min_chars and chunks:
            # 如果最后一块太小，合并到上一个块
            chunks[-1]["content"] += current_chunk
            chunks[-1]["metadata"]["end"] = chunks[-1]["metadata"]["start"] + len(chunks[-1]["content"])
        elif current_chunk:
            # 唯一的一块，直接添加
            chunks.append(self._create_chunk(current_chunk, current_start, metadata))
        
        return chunks
    
    def _split_long_sentence(
        self,
        sentence: str,
        start_pos: int,
        metadata: Optional[Dict]
    ) -> List[Dict]:
        """
        分割过长的句子
        
        按字符强制切分，确保每块都在 [min_chars, max_chars] 范围内。
        
        Args:
            sentence: 超长句子
            start_pos: 句子起始位置
            metadata: 元数据
            
        Returns:
            分割后的块列表
        """
        chunks = []
        pos = 0
        
        while pos < len(sentence):
            # 计算剩余长度
            remaining = len(sentence) - pos
            
            # 如果剩余长度在允许范围内
            if remaining <= self.max_chars:
                chunk_text = sentence[pos:]
                chunks.append(self._create_chunk(chunk_text, start_pos + pos, metadata))
                break
            
            # 否则按 max_chars 切分
            chunk_text = sentence[pos:pos + self.max_chars]
            chunks.append(self._create_chunk(chunk_text, start_pos + pos, metadata))
            pos += self.max_chars
        
        return chunks
    
    def _create_chunk(
        self,
        content: str,
        start: int,
        metadata: Optional[Dict]
    ) -> Dict:
        """
        创建块对象
        
        Args:
            content: 块内容
            start: 起始位置
            metadata: 元数据
            
        Returns:
            块字典
        """
        end = start + len(content)
        
        # 合并元数据
        chunk_metadata = {
            "start": start,
            "end": end,
        }
        if metadata:
            chunk_metadata.update(metadata)
        
        return {
            "content": content,
            "metadata": chunk_metadata
        }
