"""
记忆冲突解决器

功能：
- 冲突检测 - 使用LLM判断两条记忆是否矛盾
- 冲突解决 - 保留最新、标注变更原因、创建版本记录
- 记忆合并 - 合并相似记忆
"""

import os
import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

from sqlalchemy.orm import Session

# 设置 HuggingFace 离线模式
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

from database import (
    get_db, Memory, MemoryVersion, Persona
)


class MemoryConflictResolver:
    """记忆冲突解决器"""

    # 冲突类型
    CONFLICT_DIRECT = "direct"  # 直接矛盾（A vs 非A）
    CONFLICT_UPDATE = "update"  # 更新（旧信息 vs 新信息）
    CONFLICT_CONTEXT = "context"  # 上下文矛盾（不同情境）
    CONFLICT_NO = "none"  # 无冲突

    # 解决策略
    STRATEGY_KEEP_NEWEST = "keep_newest"  # 保留最新的
    STRATEGY_MERGE = "merge"  # 合并
    STRATEGY_CONTEXTUALIZE = "contextualize"  # 添加上下文
    STRATEGY_KEEP_BOTH = "keep_both"  # 保留两者（不同情境）

    def __init__(self, db: Session = None, llm_service=None):
        self.db = db or get_db()
        self._llm_service = llm_service

    def _get_llm_service(self):
        """Lazy load LLM service."""
        if self._llm_service is None:
            from llm_service import LLMService
            self._llm_service = LLMService()
        return self._llm_service

    def detect_conflict(self, existing_content: str, new_content: str) -> Tuple[bool, str]:
        """
        检测记忆是否冲突

        Args:
            existing_content: 现有记忆内容
            new_content: 新记忆内容

        Returns:
            (是否有冲突, 冲突类型)
        """
        # 首先使用规则快速检测
        quick_conflict, quick_type = self._quick_conflict_detect(existing_content, new_content)

        if quick_conflict:
            return True, quick_type

        # 使用LLM进行更精确的检测
        try:
            llm_conflict, llm_type = self._llm_conflict_detect(existing_content, new_content)
            return llm_conflict, llm_type
        except Exception as e:
            print(f"[ConflictResolver] LLM detection failed: {e}")
            # 回退到规则检测
            return False, self.CONFLICT_NO

    def _quick_conflict_detect(self, existing: str, new: str) -> Tuple[bool, str]:
        """快速规则检测冲突"""

        # 直接矛盾模式：检测内容是否相同但态度相反
        # 先从existing中提取内容，再检查new中是否有相反的表达
        extract_patterns = [
            # 喜欢/不喜欢模式
            (r'喜欢(.+?)(?:[，。！]|$)', '喜欢', '不喜欢'),
            (r'不喜欢(.+?)(?:[，。！]|$)', '不喜欢', '喜欢'),
            (r'爱吃(.+?)(?:[，。！]|$)', '爱吃', '不吃'),
            (r'不吃(.+?)(?:[，。！]|$)', '不吃', '爱吃'),
            # 是/不是模式
            (r'是(.+?)(?:[，。！]|$)', '是', '不是'),
            (r'不是(.+?)(?:[，。！]|$)', '不是', '是'),
            # 有/没有模式
            (r'有(.+?)(?:[，。！]|$)', '有', '没有'),
            (r'没有(.+?)(?:[，。！]|$)', '没有', '有'),
        ]

        for pattern, positive, negative in extract_patterns:
            match = re.search(pattern, existing)
            if match:
                content = match.group(1).strip()
                # 检查新内容中是否有相反的表达
                opposite_pattern = f"{negative}.*{re.escape(content)}"
                if re.search(opposite_pattern, new):
                    return True, self.CONFLICT_DIRECT

        # 反向检查：从new中提取内容，检查existing中是否有相反的表达
        for pattern, positive, negative in extract_patterns:
            match = re.search(pattern, new)
            if match:
                content = match.group(1).strip()
                opposite_pattern = f"{negative}.*{re.escape(content)}"
                if re.search(opposite_pattern, existing):
                    return True, self.CONFLICT_DIRECT

        # 更新模式：新旧信息替换
        update_indicators = [
            ("以前", "现在"),
            ("之前", "最近"),
            ("以前喜欢", "现在不喜欢"),
            ("以前不喜欢", "现在喜欢"),
        ]

        for old_ind, new_ind in update_indicators:
            if old_ind in existing and new_ind in new:
                return True, self.CONFLICT_UPDATE

        return False, self.CONFLICT_NO

    def _llm_conflict_detect(self, existing: str, new: str) -> Tuple[bool, str]:
        """使用LLM检测冲突"""
        llm = self._get_llm_service()

        prompt = f"""判断以下两条记忆是否存在矛盾或冲突：

记忆1：{existing}
记忆2：{new}

请分析：
1. 这两条记忆是否描述了相同或相似的事物？
2. 它们在内容上是否矛盾？
3. 如果有矛盾，是什么类型的矛盾？

请以JSON格式回复：
{{
    "has_conflict": true/false,
    "conflict_type": "direct/update/context/none",
    "reason": "简短解释"
}}

直接输出JSON，不要包含其他内容。"""

        try:
            response = llm.client.chat.completions.create(
                model=llm.config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=150,
                timeout=8.0  # 请求级超时保护
            )

            content = response.choices[0].message.content.strip()

            # 提取JSON
            json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                has_conflict = result.get("has_conflict", False)
                conflict_type = result.get("conflict_type", "none")
                return has_conflict, conflict_type

        except Exception as e:
            print(f"[ConflictResolver] LLM error: {e}")

        return False, self.CONFLICT_NO

    def resolve_conflict(
        self,
        existing_memory_id: int,
        new_content: str,
        conflict_type: str = None
    ) -> Optional[Memory]:
        """
        解决记忆冲突

        Args:
            existing_memory_id: 现有记忆ID
            new_content: 新记忆内容
            conflict_type: 冲突类型

        Returns:
            更新后的记忆
        """
        existing = self.db.query(Memory).filter(Memory.id == existing_memory_id).first()
        if not existing:
            return None

        # 如果未指定冲突类型，检测它
        if conflict_type is None:
            _, conflict_type = self.detect_conflict(existing.content, new_content)

        # 根据冲突类型选择解决策略
        strategy = self._select_strategy(conflict_type)

        print(f"[ConflictResolver] Resolving conflict (type: {conflict_type}, strategy: {strategy})")

        if strategy == self.STRATEGY_KEEP_NEWEST:
            return self._resolve_keep_newest(existing, new_content)
        elif strategy == self.STRATEGY_MERGE:
            return self._resolve_merge(existing, new_content)
        elif strategy == self.STRATEGY_CONTEXTUALIZE:
            return self._resolve_contextualize(existing, new_content)
        else:
            return self._resolve_keep_both(existing, new_content)

    def _select_strategy(self, conflict_type: str) -> str:
        """根据冲突类型选择解决策略"""
        strategy_map = {
            self.CONFLICT_DIRECT: self.STRATEGY_KEEP_NEWEST,
            self.CONFLICT_UPDATE: self.STRATEGY_CONTEXTUALIZE,
            self.CONFLICT_CONTEXT: self.STRATEGY_KEEP_BOTH,
            self.CONFLICT_NO: self.STRATEGY_KEEP_BOTH,
        }
        return strategy_map.get(conflict_type, self.STRATEGY_KEEP_NEWEST)

    def _resolve_keep_newest(self, existing: Memory, new_content: str) -> Memory:
        """保留最新的记忆（创建版本记录）"""
        # 创建版本记录
        version_count = self.db.query(MemoryVersion).filter(
            MemoryVersion.memory_id == existing.id
        ).count()

        version = MemoryVersion(
            memory_id=existing.id,
            version=version_count + 1,
            old_content=existing.content,
            new_content=new_content,
            change_reason=f"记忆更新：覆盖旧记忆",
            conflict_resolved=True
        )
        self.db.add(version)

        # 更新记忆
        existing.content = new_content
        existing.last_accessed = datetime.utcnow()

        self.db.commit()
        self.db.refresh(existing)

        return existing

    def _resolve_merge(self, existing: Memory, new_content: str) -> Memory:
        """合并两条记忆"""
        # 创建合并内容
        merged_content = f"{existing.content}；另外{new_content}"

        # 创建版本记录
        version_count = self.db.query(MemoryVersion).filter(
            MemoryVersion.memory_id == existing.id
        ).count()

        version = MemoryVersion(
            memory_id=existing.id,
            version=version_count + 1,
            old_content=existing.content,
            new_content=merged_content,
            change_reason="记忆合并：保留两者信息",
            conflict_resolved=True
        )
        self.db.add(version)

        existing.content = merged_content
        existing.last_accessed = datetime.utcnow()

        self.db.commit()
        self.db.refresh(existing)

        return existing

    def _resolve_contextualize(self, existing: Memory, new_content: str) -> Memory:
        """添加上下文保留两条记忆"""
        # 添加时间上下文
        now = datetime.utcnow().strftime("%Y-%m-%d")
        contextualized = f"[{now}更新] {new_content}（之前：{existing.content}）"

        # 创建版本记录
        version_count = self.db.query(MemoryVersion).filter(
            MemoryVersion.memory_id == existing.id
        ).count()

        version = MemoryVersion(
            memory_id=existing.id,
            version=version_count + 1,
            old_content=existing.content,
            new_content=contextualized,
            change_reason="记忆更新：添加上下文保留历史",
            conflict_resolved=True
        )
        self.db.add(version)

        existing.content = contextualized
        existing.last_accessed = datetime.utcnow()

        self.db.commit()
        self.db.refresh(existing)

        return existing

    def _resolve_keep_both(self, existing: Memory, new_content: str) -> Memory:
        """保留两条记忆（创建新记忆）"""
        # 创建新记忆
        new_memory = Memory(
            persona_id=existing.persona_id,
            content=new_content,
            memory_type=existing.memory_type,
            importance_score=existing.importance_score,
            created_at=datetime.utcnow()
        )
        self.db.add(new_memory)

        # 增加现有记忆的访问计数
        existing.access_count += 1
        existing.last_accessed = datetime.utcnow()

        self.db.commit()
        self.db.refresh(new_memory)

        return new_memory

    def merge_memories(self, memories: List[Memory]) -> Optional[Memory]:
        """
        合并多条相似记忆

        Args:
            memories: 要合并的记忆列表

        Returns:
            合并后的记忆
        """
        if not memories:
            return None

        if len(memories) == 1:
            return memories[0]

        # 按重要性排序
        sorted_memories = sorted(memories, key=lambda m: m.importance_score, reverse=True)

        # 使用最重要的记忆作为基础
        base_memory = sorted_memories[0]

        # 收集其他记忆的独特信息
        additional_info = []
        for memory in sorted_memories[1:]:
            # 提取独特信息
            unique_parts = self._extract_unique_info(base_memory.content, memory.content)
            if unique_parts:
                additional_info.append(unique_parts)

        if additional_info:
            # 合并内容
            merged_content = base_memory.content
            for info in additional_info[:2]:  # 最多合并2条额外信息
                merged_content += f"；{info}"

            # 创建版本记录
            version = MemoryVersion(
                memory_id=base_memory.id,
                version=self.db.query(MemoryVersion).filter(
                    MemoryVersion.memory_id == base_memory.id
                ).count() + 1,
                old_content=base_memory.content,
                new_content=merged_content,
                change_reason="记忆合并：合并相似记忆"
            )
            self.db.add(version)

            # 更新基础记忆
            base_memory.content = merged_content
            base_memory.importance_score = min(1.0, base_memory.importance_score + 0.1)

            # 删除被合并的记忆
            for memory in sorted_memories[1:]:
                self.db.delete(memory)

            self.db.commit()
            self.db.refresh(base_memory)

            print(f"[ConflictResolver] Merged {len(memories)} memories into one")

        return base_memory

    def _extract_unique_info(self, base_content: str, other_content: str) -> Optional[str]:
        """提取其他记忆中独特的信息"""
        # 简单实现：检查是否有不在基础内容中的关键词
        base_words = set(base_content)
        other_words = set(other_content)
        unique_words = other_words - base_words

        if len(unique_words) > 2:
            # 尝试提取有意义的短语
            for i in range(len(other_content) - 3):
                phrase = other_content[i:i+4]
                if phrase not in base_content and len(phrase.strip()) > 2:
                    return phrase

        return None

    def find_similar_memories(
        self,
        persona_id: int,
        threshold: float = 0.8
    ) -> List[Tuple[Memory, Memory, float]]:
        """
        查找相似的记忆对

        Args:
            persona_id: Persona ID
            threshold: 相似度阈值

        Returns:
            相似记忆对列表 [(memory1, memory2, similarity), ...]
        """
        memories = self.db.query(Memory).filter(
            Memory.persona_id == persona_id
        ).all()

        similar_pairs = []

        for i, m1 in enumerate(memories):
            for m2 in memories[i+1:]:
                similarity = self._calculate_similarity(m1.content, m2.content)
                if similarity >= threshold:
                    similar_pairs.append((m1, m2, similarity))

        return similar_pairs

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """计算文本相似度（Jaccard + 编辑距离混合）"""
        # Jaccard相似度
        words1 = set(text1.lower())
        words2 = set(text2.lower())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2
        jaccard = len(intersection) / len(union)

        # 简单的长度相似度
        len_ratio = min(len(text1), len(text2)) / max(len(text1), len(text2), 1)

        # 混合评分
        return 0.7 * jaccard + 0.3 * len_ratio

    def get_conflict_history(self, memory_id: int) -> List[Dict]:
        """
        获取记忆的冲突解决历史

        Args:
            memory_id: 记忆ID

        Returns:
            版本历史列表
        """
        versions = self.db.query(MemoryVersion).filter(
            MemoryVersion.memory_id == memory_id,
            MemoryVersion.conflict_resolved == True
        ).order_by(MemoryVersion.version).all()

        return [{
            "version": v.version,
            "old_content": v.old_content,
            "new_content": v.new_content,
            "reason": v.change_reason,
            "changed_at": v.changed_at.isoformat() if v.changed_at else None
        } for v in versions]


# Singleton
_conflict_resolver = None


def get_conflict_resolver(db: Session = None) -> MemoryConflictResolver:
    """Get or create conflict resolver singleton."""
    global _conflict_resolver
    if _conflict_resolver is None:
        _conflict_resolver = MemoryConflictResolver(db)
    return _conflict_resolver


if __name__ == "__main__":
    from database import init_database
    init_database()

    resolver = get_conflict_resolver()

    # 测试冲突检测
    test_cases = [
        ("我喜欢吃辣", "我不喜欢吃辣"),
        ("我住在上海", "我住在北京"),
        ("我喜欢看电影", "我喜欢看书"),
    ]

    for existing, new in test_cases:
        has_conflict, conflict_type = resolver.detect_conflict(existing, new)
        print(f"'{existing}' vs '{new}'")
        print(f"  Conflict: {has_conflict}, Type: {conflict_type}\n")

    print("[ConflictResolver] Service initialized successfully")