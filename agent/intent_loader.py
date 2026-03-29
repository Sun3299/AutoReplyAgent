"""
agent/intent_loader.py - 意图加载器

置信度算法：
1. 核心词*0.4 + 动作词*0.3 + 实体词*0.2 + 完整匹配*0.1
2. 多意图判断：Top1 - Top2 > 0.2 → 明确意图
3. 阈值：高(≥0.7) / 中(0.5-0.7) / 低(<0.5)
"""

import json
import os
from dataclasses import dataclass
from typing import Dict, Any, Optional, List


@dataclass
class IntentMatch:
    """意图匹配结果"""

    intent_key: str
    score: float
    knowledge_type: str
    description: str
    intent_type: str


class IntentLoader:
    """意图加载器"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "intents.json")

        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        conf = self.config.get("置信度配置", {})
        self.core_weight = conf.get("core_weight", 0.4)
        self.action_weight = conf.get("action_weight", 0.3)
        self.entity_weight = conf.get("entity_weight", 0.2)
        self.full_match_bonus = conf.get("full_match_bonus", 0.1)
        self.threshold_high = conf.get("threshold_high", 0.7)
        self.threshold_medium = conf.get("threshold_medium", 0.5)
        self.ambiguity_diff = conf.get("ambiguity_diff", 0.2)

        self._intent_info: Dict[str, Dict] = {}
        self._build_index()

    def _build_index(self):
        """构建关键词索引"""
        # 统一处理用户意图和客户意图
        for prefix, section_key in [("user", "用户意图"), ("customer", "客户意图")]:
            section = self.config.get(section_key, {}).get("intents", {})
            for intent_key, intent_data in section.items():
                kw = intent_data.get("keywords", {})
                full_key = f"{prefix}_{intent_key}"

                self._intent_info[full_key] = {
                    "type": prefix,
                    "intent_key": intent_key,
                    "description": intent_data.get("description", ""),
                    "knowledge_type": intent_data.get("knowledge_type", "internal"),
                    "core_keywords": set(kw.get("core", [])),
                    "action_keywords": set(kw.get("action", [])),
                    "entity_keywords": set(kw.get("entity", [])),
                }

    def _score_intent(self, text_lower: str, info: Dict) -> float:
        """计算单个意图的置信度"""
        score = 0.0

        # 命中核心词
        if any(kw.lower() in text_lower for kw in info["core_keywords"]):
            score += self.core_weight

        # 命中动作词
        if any(kw.lower() in text_lower for kw in info["action_keywords"]):
            score += self.action_weight

        # 命中实体词
        if any(kw.lower() in text_lower for kw in info["entity_keywords"]):
            score += self.entity_weight

        # 完整匹配
        all_kw = (
            info["core_keywords"] | info["action_keywords"] | info["entity_keywords"]
        )
        if text_lower.strip() in {k.lower() for k in all_kw}:
            score += self.full_match_bonus

        return min(score, 1.0)

    def match_all(self, text: str) -> List[IntentMatch]:
        """计算所有意图的置信度，按分数降序"""
        text_lower = text.lower()

        results = []
        for full_key, info in self._intent_info.items():
            score = self._score_intent(text_lower, info)
            if score > 0:
                results.append(
                    IntentMatch(
                        intent_key=info["intent_key"],
                        score=score,
                        knowledge_type=info["knowledge_type"],
                        description=info["description"],
                        intent_type=info["type"],
                    )
                )

        results.sort(key=lambda x: x.score, reverse=True)
        return results

    def match(self, text: str) -> Optional[IntentMatch]:
        """单意图匹配（返回最高置信度）"""
        matches = self.match_all(text)
        return matches[0] if matches else None

    def decide_route(self, text: str, session_state: Dict = None) -> Dict[str, Any]:
        """
        结合置信度决定路由

        返回：
        {
            "route": "rag/external/clarify/ambiguous/chat",
            "reason": 说明,
            "confidence": 置信度,
            "intent": IntentMatch or None,
        }
        """
        session_state = session_state or {}
        matches = self.match_all(text)

        # 无匹配 → chat
        if not matches:
            return self._chat_result(0.0, None)

        primary = matches[0]
        level = self._get_level(primary.score)
        secondary = matches[1] if len(matches) > 1 else None

        # 低置信 → chat（不触发RAG）
        if level == "low":
            return self._chat_result(primary.score, primary)

        # 中高置信：检查是否需要澄清
        if level in ("medium", "high"):
            need_clarify, clarify_msg = self._check_clarify(primary, session_state)
            if need_clarify:
                return {
                    "route": "clarify",
                    "reason": clarify_msg,
                    "confidence": primary.score,
                    "intent": primary,
                }

        # 多意图歧义
        if secondary and (primary.score - secondary.score) < self.ambiguity_diff:
            return {
                "route": "ambiguous",
                "reason": f"多意图歧义 (差值{primary.score - secondary.score:.2f})",
                "confidence": primary.score,
                "intent": primary,
            }

        # 高置信：根据 knowledge_type 路由
        if level == "high":
            return {
                "route": "external" if primary.knowledge_type == "external" else "rag",
                "reason": "高置信"
                + ("外部" if primary.knowledge_type == "external" else "内部")
                + "知识",
                "confidence": primary.score,
                "intent": primary,
            }

        # 中置信 → rag
        return {
            "route": "rag",
            "reason": "中置信RAG兜底",
            "confidence": primary.score,
            "intent": primary,
        }

    def _chat_result(
        self, confidence: float, intent: Optional[IntentMatch]
    ) -> Dict[str, Any]:
        """构建chat路由结果"""
        return {
            "route": "chat",
            "reason": "低置信/无意图，直接LLM回复",
            "confidence": confidence,
            "intent": intent,
        }

    def _get_level(self, score: float) -> str:
        """置信度等级"""
        if score >= self.threshold_high:
            return "high"
        if score >= self.threshold_medium:
            return "medium"
        return "low"

    def _check_clarify(self, intent: IntentMatch, session_state: Dict) -> tuple:
        """检查是否需要澄清"""
        checks = {
            "query_order": ("order_id", "请提供您的订单号"),
            "query_logistics": ("logistics_id", "请提供您的快递单号"),
        }
        check = checks.get(intent.intent_key)
        if check and not session_state.get(check[0]):
            return True, check[1]
        return False, ""


# 按channel缓存loader
_loaders: Dict[str, IntentLoader] = {}


def get_intent_loader(channel: str = "web") -> IntentLoader:
    if channel not in _loaders:
        _loaders[channel] = IntentLoader()
    return _loaders[channel]
