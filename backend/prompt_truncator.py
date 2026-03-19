"""
Prompt长度限制工具

解决"迷失在中间"(Lost in the Middle)问题：
- 使用tiktoken计算Token数量
- 按优先级截断上下文
- 死保Hot Memory和最近对话历史
"""

import os
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter

# 设置 HuggingFace 离线模式
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

# 尝试导入tiktoken
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    print("[PromptTruncator] Warning: tiktoken not available, using character-based estimation")


class PromptTruncator:
    """Prompt长度限制器"""

    # 默认Token限制
    DEFAULT_MAX_TOKENS = 2000
    DEFAULT_MAX_CHARS = 4000  # 备用：字符数限制

    # 上下文优先级（从高到低）
    # Hot Memory > 最近对话 > Scratchpad > Journals > Cold Memory
    PRIORITY_ORDER = [
        "hot_memory",       # 最高优先级：核心特征
        "recent_history",   # 最近2轮对话
        "scratchpad",       # 当前会话状态
        "journals",         # 近期日记
        "cold_memory",      # 最低优先级：历史记忆
        "legacy_memory"     # 传统记忆检索
    ]

    # 各类型保留比例
    RETENTION_RATIO = {
        "hot_memory": 1.0,       # 100%保留
        "recent_history": 0.9,   # 90%保留
        "scratchpad": 0.8,       # 80%保留
        "journals": 0.5,         # 50%保留
        "cold_memory": 0.3,      # 30%保留
        "legacy_memory": 0.4     # 40%保留
    }

    def __init__(self, model_name: str = "gpt-3.5-turbo"):
        """初始化Token计数器"""
        self.model_name = model_name
        self.encoder = None

        if TIKTOKEN_AVAILABLE:
            try:
                # 尝试获取模型对应的编码器
                self.encoder = tiktoken.encoding_for_model(model_name)
            except KeyError:
                # 模型不支持，使用cl100k_base（GPT-3.5/GPT-4通用）
                self.encoder = tiktoken.get_encoding("cl100k_base")
            except Exception as e:
                print(f"[PromptTruncator] Error initializing tiktoken: {e}")

    def count_tokens(self, text: str) -> int:
        """计算文本的Token数量"""
        if not text:
            return 0

        if self.encoder:
            try:
                return len(self.encoder.encode(text))
            except Exception:
                pass

        # 备用：字符数估算（中文约1.5字符/token，英文约4字符/token）
        # 保守估计：每2个字符约1个token
        return len(text) // 2

    def count_messages_tokens(self, messages: List[Dict[str, str]]) -> int:
        """计算消息列表的总Token数"""
        total = 0
        for msg in messages:
            # 每条消息有角色和内容的开销
            total += 4  # 消息格式开销
            total += self.count_tokens(msg.get("role", ""))
            total += self.count_tokens(msg.get("content", ""))
        total += 2  # 对话结束标记
        return total

    def truncate_context(
        self,
        contexts: Dict[str, str],
        max_tokens: int = DEFAULT_MAX_TOKENS,
        system_prompt_tokens: int = 500  # 为System Prompt预留的Token
    ) -> Tuple[Dict[str, str], Dict[str, Any]]:
        """
        按优先级截断上下文

        Args:
            contexts: 各层记忆上下文字典
            max_tokens: 最大Token限制
            system_prompt_tokens: 系统提示词占用的Token

        Returns:
            (截断后的上下文, 统计信息)
        """
        available_tokens = max_tokens - system_prompt_tokens
        if available_tokens < 500:
            available_tokens = 500  # 至少保留500 tokens给上下文

        result = {}
        stats = {
            "original_tokens": {},
            "truncated_tokens": {},
            "truncation_ratio": {},
            "total_original": 0,
            "total_truncated": 0
        }

        # 计算原始Token数
        for key in self.PRIORITY_ORDER:
            if key in contexts:
                tokens = self.count_tokens(contexts[key])
                stats["original_tokens"][key] = tokens
                stats["total_original"] += tokens

        # 按优先级分配Token
        remaining_tokens = available_tokens

        for key in self.PRIORITY_ORDER:
            if key not in contexts:
                continue

            original = contexts[key]
            original_tokens = stats["original_tokens"][key]
            retention = self.RETENTION_RATIO.get(key, 0.5)

            # 计算该类型可用的Token
            max_for_type = int(available_tokens * retention)
            max_for_type = min(max_for_type, remaining_tokens)

            if original_tokens <= max_for_type:
                # 无需截断
                result[key] = original
                stats["truncated_tokens"][key] = original_tokens
                remaining_tokens -= original_tokens
            else:
                # 需要截断
                truncated = self._truncate_text(original, max_for_type)
                result[key] = truncated
                stats["truncated_tokens"][key] = self.count_tokens(truncated)
                remaining_tokens -= stats["truncated_tokens"][key]

            stats["truncation_ratio"][key] = (
                stats["truncated_tokens"][key] / original_tokens if original_tokens > 0 else 0
            )

        stats["total_truncated"] = sum(stats["truncated_tokens"].values())

        return result, stats

    def _truncate_text(self, text: str, max_tokens: int) -> str:
        """
        截断文本到指定Token数

        优先保留开头和结尾
        """
        if self.count_tokens(text) <= max_tokens:
            return text

        # 估算字符数
        estimated_chars = max_tokens * 2

        if len(text) <= estimated_chars:
            return text

        # 保留开头70%，结尾30%
        head_chars = int(estimated_chars * 0.7)
        tail_chars = int(estimated_chars * 0.3)

        head = text[:head_chars]
        tail = text[-tail_chars:]

        return f"{head}...\n[已截断]...\n{tail}"

    def truncate_messages(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = DEFAULT_MAX_TOKENS,
        keep_system: bool = True
    ) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
        """
        截断消息列表

        优先保留：System消息 > 最近的用户消息 > 历史消息

        Args:
            messages: 消息列表
            max_tokens: 最大Token限制
            keep_system: 是否保留System消息

        Returns:
            (截断后的消息列表, 统计信息)
        """
        if not messages:
            return [], {"total_original": 0, "total_truncated": 0}

        stats = {
            "total_original": self.count_messages_tokens(messages),
            "total_truncated": 0,
            "removed_messages": 0
        }

        current_tokens = self.count_messages_tokens(messages)
        if current_tokens <= max_tokens:
            stats["total_truncated"] = current_tokens
            return messages, stats

        result = []

        # 分离System消息和其他消息
        system_messages = []
        other_messages = []

        for msg in messages:
            if msg.get("role") == "system":
                system_messages.append(msg)
            else:
                other_messages.append(msg)

        # 先添加System消息
        if keep_system:
            result.extend(system_messages)

        current_tokens = self.count_messages_tokens(result)

        # 从最新的消息开始添加（保留最近的对话）
        remaining_tokens = max_tokens - current_tokens

        # 倒序遍历，保留最近的
        for msg in reversed(other_messages):
            msg_tokens = self.count_messages_tokens([msg])

            if msg_tokens <= remaining_tokens:
                result.insert(-len([m for m in result if m.get("role") != "system"]), msg)
                remaining_tokens -= msg_tokens
            else:
                stats["removed_messages"] += 1

        stats["total_truncated"] = self.count_messages_tokens(result)

        return result, stats

    def optimize_for_llm(
        self,
        messages: List[Dict[str, str]],
        contexts: Dict[str, str],
        max_tokens: int = DEFAULT_MAX_TOKENS
    ) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
        """
        综合优化：先截断上下文，再构建消息列表

        这是推荐使用的入口方法

        Args:
            messages: 原始消息列表（不含记忆上下文）
            contexts: 各层记忆上下文
            max_tokens: 最大Token限制

        Returns:
            (优化后的消息列表, 统计信息)
        """
        # 计算基础消息的Token数
        base_tokens = self.count_messages_tokens(messages)

        # 截断上下文
        truncated_contexts, context_stats = self.truncate_context(
            contexts,
            max_tokens=max_tokens,
            system_prompt_tokens=base_tokens
        )

        # 构建最终消息列表
        result = []

        # 添加原始System消息
        for msg in messages:
            if msg.get("role") == "system":
                result.append(msg)
                break  # 只取第一个System消息

        # 添加记忆上下文（按优先级）
        for key in self.PRIORITY_ORDER:
            if key in truncated_contexts and truncated_contexts[key]:
                result.append({
                    "role": "system",
                    "content": truncated_contexts[key]
                })

        # 添加其他消息（对话历史）
        for msg in messages:
            if msg.get("role") != "system":
                result.append(msg)

        # 最终检查是否超限
        final_tokens = self.count_messages_tokens(result)
        if final_tokens > max_tokens:
            # 再次截断
            result, msg_stats = self.truncate_messages(result, max_tokens)
            context_stats["final_truncation"] = True
            context_stats["final_tokens"] = msg_stats["total_truncated"]
        else:
            context_stats["final_truncation"] = False
            context_stats["final_tokens"] = final_tokens

        context_stats["optimization_applied"] = True

        return result, context_stats


# Singleton
_truncator = None


def get_prompt_truncator(model_name: str = "gpt-3.5-turbo") -> PromptTruncator:
    """Get or create prompt truncator singleton."""
    global _truncator
    if _truncator is None:
        _truncator = PromptTruncator(model_name)
    return _truncator


if __name__ == "__main__":
    truncator = get_prompt_truncator()

    # 测试Token计数
    test_text = "这是一段测试文本，用于验证Token计数功能。"
    tokens = truncator.count_tokens(test_text)
    print(f"Text: {test_text}")
    print(f"Tokens: {tokens}")

    # 测试上下文截断
    contexts = {
        "hot_memory": "【核心记忆】\n常用口头禅：哈哈、嘿嘿\n核心特征：性格开朗",
        "scratchpad": "【当前会话状态】\n当前任务：聊天\n情绪：开心",
        "journals": "【近期日记】\n- 03月16日日记：今天聊了很多开心的事..." * 10,
        "cold_memory": "【历史记忆】\n" + "这是一条很长的历史记忆..." * 50
    }

    truncated, stats = truncator.truncate_context(contexts, max_tokens=300)

    print("\n=== Truncation Stats ===")
    for key in stats["original_tokens"]:
        print(f"{key}: {stats['original_tokens'][key]} -> {stats['truncated_tokens'][key]} ({stats['truncation_ratio'][key]*100:.0f}%)")
    print(f"\nTotal: {stats['total_original']} -> {stats['total_truncated']}")

    print("\n[PromptTruncator] Service initialized successfully")