"""
agent/intent_loader.py - 意图加载器（支持置信度计算+多意图判断）

核心算法：
1. 置信度 = 核心词*0.4 + 动作词*0.3 + 实体词*0.2 + 完整匹配*0.1
2. 多意图判断：Top1 - Top2 > 0.2 → 明确意图，否则多意图
3. 阈值判断：高(≥0.7) / 中(0.5-0.7) / 低(<0.5)
"""

import json
import os
from typing import Dict, Any, Optional, List


class IntentMatch:
    """意图匹配结果"""
    def __init__(self, intent_key: str, score: float, knowledge_type: str, 
                 description: str, intent_type: str):
        self.intent_key = intent_key
        self.score = score
        self.knowledge_type = knowledge_type
        self.description = description
        self.intent_type = intent_type


class IntentLoader:
    """意图加载器"""
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "intents.json")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # 置信度配置
        conf = self.config.get("置信度配置", {})
        self.core_weight = conf.get("core_weight", 0.4)
        self.action_weight = conf.get("action_weight", 0.3)
        self.entity_weight = conf.get("entity_weight", 0.2)
        self.full_match_bonus = conf.get("full_match_bonus", 0.1)
        self.threshold_high = conf.get("threshold_high", 0.7)
        self.threshold_medium = conf.get("threshold_medium", 0.5)
        self.ambiguity_diff = conf.get("ambiguity_diff", 0.2)
        
        # 构建索引
        self._build_index()
    
    def _build_index(self):
        """构建关键词索引"""
        self._intent_info = {}
        
        # 用户意图
        user_intents = self.config.get("用户意图", {}).get("intents", {})
        for intent_key, intent_data in user_intents.items():
            kw = intent_data.get("keywords", {})
            keywords = []
            keywords.extend(kw.get("core", []))
            keywords.extend(kw.get("action", []))
            keywords.extend(kw.get("entity", []))
            
            self._intent_info[f"user_{intent_key}"] = {
                "type": "用户意图",
                "intent_key": intent_key,
                "description": intent_data.get("description", ""),
                "knowledge_type": intent_data.get("knowledge_type", "internal"),
                "core_keywords": set(kw.get("core", [])),
                "action_keywords": set(kw.get("action", [])),
                "entity_keywords": set(kw.get("entity", [])),
                "all_keywords": keywords
            }
        
        # 客户意图
        customer_intents = self.config.get("客户意图", {}).get("intents", {})
        for intent_key, intent_data in customer_intents.items():
            kw = intent_data.get("keywords", {})
            keywords = []
            keywords.extend(kw.get("core", []))
            keywords.extend(kw.get("action", []))
            keywords.extend(kw.get("entity", []))
            
            self._intent_info[f"customer_{intent_key}"] = {
                "type": "客户意图",
                "intent_key": intent_key,
                "description": intent_data.get("description", ""),
                "knowledge_type": "internal",
                "core_keywords": set(kw.get("core", [])),
                "action_keywords": set(kw.get("action", [])),
                "entity_keywords": set(kw.get("entity", [])),
                "all_keywords": keywords
            }
    
    def match_all(self, text: str) -> List[IntentMatch]:
        """
        计算所有意图的置信度
        
        算法：
        - 命中核心词: +0.4
        - 命中动作词: +0.3
        - 命中实体词: +0.2
        - 完整匹配: +0.1
        """
        text_lower = text.lower()
        results = []
        
        for full_key, info in self._intent_info.items():
            score = 0.0
            matched_types = []
            
            # 检查核心词
            for kw in info["core_keywords"]:
                if kw.lower() in text_lower:
                    score += self.core_weight
                    matched_types.append("core")
            
            # 检查动作词
            for kw in info["action_keywords"]:
                if kw.lower() in text_lower:
                    score += self.action_weight
                    matched_types.append("action")
            
            # 检查实体词
            for kw in info["entity_keywords"]:
                if kw.lower() in text_lower:
                    score += self.entity_weight
                    matched_types.append("entity")
            
            # 完整匹配加分
            if text_lower.strip() in [k.lower() for k in info["all_keywords"]]:
                score += self.full_match_bonus
            
            # 归一化到0-1
            score = min(score, 1.0)
            
            if score > 0:
                results.append(IntentMatch(
                    intent_key=info["intent_key"],
                    score=score,
                    knowledge_type=info["knowledge_type"],
                    description=info["description"],
                    intent_type=info["type"]
                ))
        
        # 按置信度排序
        results.sort(key=lambda x: x.score, reverse=True)
        return results
    
    def match(self, text: str) -> Optional[IntentMatch]:
        """单意图匹配（返回最高置信度）"""
        matches = self.match_all(text)
        return matches[0] if matches else None
    
    def match_with_ambiguity(self, text: str) -> Dict[str, Any]:
        """
        多意图判断
        
        返回：
        {
            "primary": 最高置信度意图,
            "secondary": 第二高置信度意图,
            "diff": 差值,
            "is_ambiguous": 是否多意图,
            "confidence_level": "high/medium/low"
        }
        """
        matches = self.match_all(text)
        
        if not matches:
            return {"is_ambiguous": False, "confidence_level": "low"}
        
        primary = matches[0]
        
        # 只有一个
        if len(matches) == 1:
            return {
                "primary": primary,
                "secondary": None,
                "diff": 1.0,
                "is_ambiguous": False,
                "confidence_level": self._get_level(primary.score)
            }
        
        secondary = matches[1]
        diff = primary.score - secondary.score
        
        # 差值 < 0.2 为多意图/歧义
        is_ambiguous = diff < self.ambiguity_diff
        
        return {
            "primary": primary,
            "secondary": secondary,
            "diff": diff,
            "is_ambiguous": is_ambiguous,
            "confidence_level": self._get_level(primary.score)
        }
    
    def _get_level(self, score: float) -> str:
        """置信度等级"""
        if score >= self.threshold_high:
            return "high"
        elif score >= self.threshold_medium:
            return "medium"
        else:
            return "low"
    
    def decide_route(self, text: str, session_state: Dict = None) -> Dict[str, Any]:
        """
        结合置信度决定路径
        
        返回：
        {
            "route": "direct/rag/external/clarify/ambiguous",
            "reason": 说明,
            "confidence": 置信度,
            "intent": 意图,
            "need_clarify": 是否需要澄清
        }
        """
        session_state = session_state or {}
        result = self.match_with_ambiguity(text)
        
        # 置信度判断（先检查置信度，低置信不触发 clarify）
        level = result.get("confidence_level", "low")
        
        # 低置信 → RAG兜底
        if level == "low":
            return {
                "route": "rag",
                "reason": "低置信RAG兜底",
                "confidence": result.get("primary", IntentMatch("",0,"","","")).score if result.get("primary") else 0,
                "intent": result.get("primary"),
                "need_clarify": False
            }
        
        # 检查是否需要澄清（参数缺失）- 只有中高置信才检查
        need_clarify, clarify_msg = self._check_clarify(result.get("primary"), session_state)
        
        if need_clarify:
            return {
                "route": "clarify",
                "reason": "参数缺失",
                "confidence": result.get("primary", IntentMatch("",0,"","","")).score if result.get("primary") else 0,
                "intent": result.get("primary"),
                "need_clarify": True,
                "clarify_message": clarify_msg
            }
        
        # 多意图
        if result.get("is_ambiguous"):
            return {
                "route": "ambiguous",
                "reason": f"多意图歧义 (差值{result.get('diff'):.2f})",
                "confidence": result.get("primary", IntentMatch("",0,"","","")).score if result.get("primary") else 0,
                "intent": result.get("primary"),
                "secondary": result.get("secondary"),
                "need_clarify": False
            }
        
        # 高置信 → 直接执行
        if level == "high":
            knowledge = result.get("primary", IntentMatch("","","","","")).knowledge_type
            if knowledge == "external":
                return {
                    "route": "external",
                    "reason": "高置信外部知识",
                    "confidence": result.get("primary", IntentMatch("",0,"","","")).score if result.get("primary") else 0,
                    "intent": result.get("primary"),
                    "need_clarify": False
                }
            else:
                return {
                    "route": "rag",
                    "reason": "高置信内部知识",
                    "confidence": result.get("primary", IntentMatch("",0,"","","")).score if result.get("primary") else 0,
                    "intent": result.get("primary"),
                    "need_clarify": False
                }
        
        # 中置信 → RAG兜底
        if level == "medium":
            return {
                "route": "rag",
                "reason": "中置信RAG兜底",
                "confidence": result.get("primary", IntentMatch("",0,"","","")).score if result.get("primary") else 0,
                "intent": result.get("primary"),
                "need_clarify": False
            }
        
        # 低置信 / 意图不明 → 走 LLM 直接回复
        return {
            "route": "chat",
            "reason": "低置信/无意图，直接LLM回复",
            "confidence": result.get("primary", IntentMatch("",0,"","","")).score if result.get("primary") else 0,
            "intent": result.get("primary"),
            "need_clarify": False
        }
    
    def _check_clarify(self, intent_match: Optional[IntentMatch], session_state: Dict) -> tuple:
        """检查是否需要澄清"""
        if not intent_match:
            return False, ""
        
        intent_key = intent_match.intent_key
        session_state = session_state or {}
        
        # 查订单需要订单号
        if intent_key == "query_order" and not session_state.get("order_id"):
            return True, "请提供您的订单号"
        
        # 查物流需要物流单号
        if intent_key == "query_logistics" and not session_state.get("logistics_id"):
            return True, "请提供您的快递单号"
        
        return False, ""


_loader = None

def get_intent_loader(channel: str = None) -> IntentLoader:
    global _loader
    if _loader is None:
        _loader = IntentLoader()
    return _loader
