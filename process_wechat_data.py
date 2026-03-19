"""
微信聊天数据处理脚本

处理messages.json文件，提取：
1. 文本消息对话对
2. 表情包使用记录
3. 用户画像数据
4. 导入到数据库

数据格式说明：
- type=1: 文本消息
- type=3: 图片
- type=47: 表情包
- type=34: 语音
- isSent=true: 我发送的
- isSent=false: 对方发送的
"""

import json
import os
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict

# 添加backend目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from database import get_db, init_database, Persona, ChatHistory


@dataclass
class ProcessedMessage:
    """处理后的消息"""
    timestamp: datetime
    sender_id: str
    sender_name: str
    is_sent_by_me: bool
    content: str
    message_type: str  # text, emoji, image, voice, system
    emoji_md5: Optional[str] = None


@dataclass
class ConversationPair:
    """对话对"""
    user_message: str
    assistant_response: str
    user_emojis: List[str]  # 用户消息中的表情包MD5
    assistant_emojis: List[str]  # 助手回复中的表情包MD5
    timestamp: datetime
    context: List[str]  # 上下文消息


class WeChatDataProcessor:
    """微信聊天数据处理类"""

    # 消息类型映射
    MESSAGE_TYPES = {
        1: "text",       # 文本
        3: "image",      # 图片
        34: "voice",     # 语音
        43: "video",     # 视频
        47: "emoji",     # 表情包
        10000: "system", # 系统消息
    }

    # 需要处理的消息类型（其他类型忽略）
    VALID_TYPES = {1, 47, 3}  # 文本、表情、图片

    def __init__(self, json_path: str, emoji_classification_path: str = None):
        self.json_path = json_path
        self.messages: List[ProcessedMessage] = []
        self.conversation_pairs: List[ConversationPair] = []

        # 发送者信息
        self.my_id: str = None
        self.my_name: str = None
        self.target_id: str = None
        self.target_name: str = None

        # 加载表情包分类数据
        self.emoji_classification = {}
        if emoji_classification_path:
            self._load_emoji_classification(emoji_classification_path)
        else:
            default_path = os.path.join(
                os.path.dirname(json_path),
                "emoji_classification.jsonl"
            )
            if os.path.exists(default_path):
                self._load_emoji_classification(default_path)

        # 统计信息
        self.stats = {
            "total_messages": 0,
            "text_messages": 0,
            "emoji_messages": 0,
            "conversation_pairs": 0,
        }

    def _load_emoji_classification(self, path: str):
        """加载表情包分类数据"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        filename = data.get('file_name', '')
                        if filename:
                            md5 = filename.replace('.gif', '').replace('.png', '')
                            self.emoji_classification[md5] = {
                                'top_category': data.get('top_category', '其他'),
                                'sub_category': data.get('sub_category', ''),
                                'description': data.get('description', ''),
                            }
                    except json.JSONDecodeError:
                        continue
            print(f"[Processor] 加载了 {len(self.emoji_classification)} 个表情包分类")
        except Exception as e:
            print(f"[Processor] 加载表情包分类失败: {e}")

    def load_messages(self) -> List[ProcessedMessage]:
        """加载并解析消息"""
        print(f"[Processor] 正在加载 {self.json_path} ...")

        with open(self.json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        raw_messages = data.get('messages', [])
        self.stats["total_messages"] = len(raw_messages)

        # 识别发送者
        self._identify_senders(raw_messages)

        # 解析消息
        for msg in raw_messages:
            processed = self._process_message(msg)
            if processed:
                self.messages.append(processed)
                if processed.message_type == "text":
                    self.stats["text_messages"] += 1
                elif processed.message_type == "emoji":
                    self.stats["emoji_messages"] += 1

        # 按时间排序
        self.messages.sort(key=lambda m: m.timestamp)

        print(f"[Processor] 解析了 {len(self.messages)} 条有效消息")
        print(f"  - 我: {self.my_name} ({self.my_id})")
        print(f"  - 对方: {self.target_name} ({self.target_id})")

        return self.messages

    def _identify_senders(self, messages: List[dict]):
        """识别发送者信息"""
        for msg in messages[:100]:  # 只检查前100条
            is_sent = msg.get('isSent', False)
            sender_id = msg.get('senderUsername', '')
            sender_name = msg.get('senderDisplayName', '')

            if is_sent and not self.my_id:
                self.my_id = sender_id
                self.my_name = sender_name
            elif not is_sent and not self.target_id:
                self.target_id = sender_id
                self.target_name = sender_name

            if self.my_id and self.target_id:
                break

    def _process_message(self, msg: dict) -> Optional[ProcessedMessage]:
        """处理单条消息"""
        msg_type = msg.get('type', 0)

        # 只处理有效类型
        if msg_type not in self.VALID_TYPES:
            return None

        # 跳过系统消息
        if msg_type == 10000:
            return None

        # 解析时间
        timestamp_str = msg.get('createTimeText', '')
        try:
            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return None

        # 获取内容
        content = msg.get('content', '')
        emoji_md5 = msg.get('emojiMd5', '')

        # 确定消息类型
        message_type = self.MESSAGE_TYPES.get(msg_type, "unknown")

        # 对于表情包消息，转换内容格式
        if msg_type == 47 and emoji_md5:
            content = f"[表情：{emoji_md5}]"

        # 对于图片消息，标记但不处理
        if msg_type == 3:
            content = "[图片]"

        return ProcessedMessage(
            timestamp=timestamp,
            sender_id=msg.get('senderUsername', ''),
            sender_name=msg.get('senderDisplayName', ''),
            is_sent_by_me=msg.get('isSent', False),
            content=content,
            message_type=message_type,
            emoji_md5=emoji_md5 if msg_type == 47 else None
        )

    def extract_conversation_pairs(
        self,
        max_time_gap: int = 300,  # 最大时间间隔（秒）
        context_window: int = 3   # 上下文窗口
    ) -> List[ConversationPair]:
        """
        提取对话对

        逻辑：
        1. 找到对方发送的消息（用户消息）
        2. 找到紧随其后的我方消息（助手回复）
        3. 时间间隔不超过max_time_gap秒
        """
        print("[Processor] 正在提取对话对...")

        pairs = []

        i = 0
        while i < len(self.messages):
            msg = self.messages[i]

            # 找到对方发送的消息
            if not msg.is_sent_by_me and msg.message_type in ["text", "emoji"]:
                user_msg = msg
                user_emojis = [msg.emoji_md5] if msg.emoji_md5 else []

                # 收集连续的用户消息
                j = i + 1
                while j < len(self.messages):
                    next_msg = self.messages[j]
                    if next_msg.is_sent_by_me:
                        break
                    if next_msg.message_type == "text":
                        user_msg.content += " " + next_msg.content
                    if next_msg.emoji_md5:
                        user_emojis.append(next_msg.emoji_md5)
                    j += 1

                # 找助手回复（我方消息）
                if j < len(self.messages):
                    assistant_msg = self.messages[j]
                    if assistant_msg.is_sent_by_me:
                        # 检查时间间隔
                        time_gap = (assistant_msg.timestamp - user_msg.timestamp).total_seconds()

                        if time_gap <= max_time_gap:
                            # 收集连续的助手消息
                            assistant_content = assistant_msg.content
                            assistant_emojis = [assistant_msg.emoji_md5] if assistant_msg.emoji_md5 else []

                            k = j + 1
                            while k < len(self.messages) and k < j + 5:  # 最多合并5条
                                next_msg = self.messages[k]
                                if not next_msg.is_sent_by_me:
                                    break
                                time_gap_next = (next_msg.timestamp - assistant_msg.timestamp).total_seconds()
                                if time_gap_next > 60:  # 超过1分钟不算连续
                                    break
                                if next_msg.message_type == "text":
                                    assistant_content += " " + next_msg.content
                                if next_msg.emoji_md5:
                                    assistant_emojis.append(next_msg.emoji_md5)
                                k += 1

                            # 获取上下文
                            context_start = max(0, i - context_window)
                            context = [
                                f"{m.sender_name}: {m.content}"
                                for m in self.messages[context_start:i]
                            ]

                            pair = ConversationPair(
                                user_message=user_msg.content.strip(),
                                assistant_response=assistant_content.strip(),
                                user_emojis=user_emojis,
                                assistant_emojis=assistant_emojis,
                                timestamp=user_msg.timestamp,
                                context=context
                            )
                            pairs.append(pair)

                        i = j
                        continue

            i += 1

        self.conversation_pairs = pairs
        self.stats["conversation_pairs"] = len(pairs)

        print(f"[Processor] 提取了 {len(pairs)} 个对话对")

        return pairs

    def analyze_emoji_usage(self) -> Dict[str, Any]:
        """分析表情包使用情况"""
        # 我方表情包使用
        my_emojis = []
        my_emoji_messages = 0
        my_text_messages = 0

        # 对方表情包使用
        target_emojis = []
        target_emoji_messages = 0
        target_text_messages = 0

        # 场景分析
        scenario_keywords = {
            "开心": ["哈哈", "嘿嘿", "嘻嘻", "太好了", "开心", "高兴", "棒", "赞"],
            "难过": ["难过", "伤心", "哭", "泪", "郁闷"],
            "调侃": ["哈哈", "笑死", "逗", "搞笑", "奇葩"],
            "安慰": ["抱抱", "没事", "别难过", "加油"],
            "惊讶": ["哇", "天哪", "卧槽", "不是吧"],
            "喜欢": ["喜欢", "爱了", "想要", "好看", "可爱"],
            "无奈": ["算了", "没办法", "无语", "服了"],
        }

        my_scenarios = []
        target_scenarios = []

        for msg in self.messages:
            if msg.is_sent_by_me:
                if msg.emoji_md5:
                    my_emojis.append(msg.emoji_md5)
                    my_emoji_messages += 1
                    # 检测场景
                    for scenario, keywords in scenario_keywords.items():
                        if any(kw in msg.content for kw in keywords):
                            my_scenarios.append(scenario)
                            break
                elif msg.message_type == "text":
                    my_text_messages += 1
            else:
                if msg.emoji_md5:
                    target_emojis.append(msg.emoji_md5)
                    target_emoji_messages += 1
                    for scenario, keywords in scenario_keywords.items():
                        if any(kw in msg.content for kw in keywords):
                            target_scenarios.append(scenario)
                            break
                elif msg.message_type == "text":
                    target_text_messages += 1

        # 计算使用率
        my_total = my_emoji_messages + my_text_messages
        target_total = target_emoji_messages + target_text_messages

        my_rate = my_emoji_messages / my_total if my_total > 0 else 0
        target_rate = target_emoji_messages / target_total if target_total > 0 else 0

        # 获取表情包类型
        def get_emoji_types(emoji_md5s):
            types = []
            for md5 in emoji_md5s:
                if md5 in self.emoji_classification:
                    types.append(self.emoji_classification[md5].get('top_category', '其他'))
            return types

        my_types = get_emoji_types(my_emojis)
        target_types = get_emoji_types(target_emojis)

        return {
            "my_emoji_usage": {
                "total_emojis": len(my_emojis),
                "emoji_messages": my_emoji_messages,
                "text_messages": my_text_messages,
                "usage_rate": round(my_rate, 3),
                "frequency": self._calculate_frequency(my_rate),
                "top_emojis": [md5 for md5, _ in Counter(my_emojis).most_common(10)],
                "top_types": [t for t, _ in Counter(my_types).most_common(5)],
                "top_scenarios": [s for s, _ in Counter(my_scenarios).most_common(5)],
            },
            "target_emoji_usage": {
                "total_emojis": len(target_emojis),
                "emoji_messages": target_emoji_messages,
                "text_messages": target_text_messages,
                "usage_rate": round(target_rate, 3),
                "frequency": self._calculate_frequency(target_rate),
                "top_emojis": [md5 for md5, _ in Counter(target_emojis).most_common(10)],
                "top_types": [t for t, _ in Counter(target_types).most_common(5)],
                "top_scenarios": [s for s, _ in Counter(target_scenarios).most_common(5)],
            }
        }

    def _calculate_frequency(self, usage_rate: float) -> str:
        """计算使用频率级别"""
        if usage_rate == 0:
            return "none"
        elif usage_rate < 0.2:
            return "low"
        elif usage_rate < 0.5:
            return "medium"
        else:
            return "high"

    def import_to_database(self, persona_name: str = None) -> int:
        """
        导入到数据库

        Returns:
            导入的对话对数量
        """
        print("[Processor] 正在导入数据库...")

        # 初始化数据库
        init_database()

        db = get_db()

        try:
            # 创建或获取Persona
            name = persona_name or self.target_name or "微信好友"
            persona = db.query(Persona).filter(Persona.name == name).first()

            if not persona:
                persona = Persona(
                    name=name,
                    description=f"从微信聊天记录导入 - {self.target_name}",
                    response_style="casual"
                )
                db.add(persona)
                db.commit()
                db.refresh(persona)
                print(f"[Processor] 创建Persona: {name} (ID: {persona.id})")
            else:
                print(f"[Processor] 使用已有Persona: {name} (ID: {persona.id})")

            # 分析表情包使用
            emoji_analysis = self.analyze_emoji_usage()

            # 更新Persona的表情包行为
            my_usage = emoji_analysis["my_emoji_usage"]
            persona.emoji_usage_frequency = my_usage["frequency"]
            persona.emoji_usage_rate = my_usage["usage_rate"]
            persona.emoji_scenario_prefs = my_usage["top_scenarios"]
            persona.emoji_type_prefs = my_usage["top_types"]

            # 导入对话对
            imported_count = 0
            for pair in self.conversation_pairs:
                # 检查是否已存在
                existing = db.query(ChatHistory).filter(
                    ChatHistory.persona_id == persona.id,
                    ChatHistory.user_message == pair.user_message,
                    ChatHistory.assistant_response == pair.assistant_response
                ).first()

                if not existing:
                    chat_history = ChatHistory(
                        persona_id=persona.id,
                        user_message=pair.user_message,
                        assistant_response=pair.assistant_response,
                        conversation_context="\n".join(pair.context) if pair.context else None,
                        topics=[],
                        sentiment="neutral"
                    )
                    db.add(chat_history)
                    imported_count += 1

            db.commit()
            print(f"[Processor] 导入了 {imported_count} 条对话记录")

            return persona.id

        except Exception as e:
            print(f"[Processor] 导入错误: {e}")
            db.rollback()
            raise
        finally:
            db.close()

    def export_to_json(self, output_path: str):
        """导出处理结果到JSON"""
        data = {
            "source": self.json_path,
            "sender_info": {
                "my_name": self.my_name,
                "my_id": self.my_id,
                "target_name": self.target_name,
                "target_id": self.target_id,
            },
            "stats": self.stats,
            "emoji_analysis": self.analyze_emoji_usage(),
            "conversation_pairs": [
                {
                    "user_message": pair.user_message,
                    "assistant_response": pair.assistant_response,
                    "user_emojis": pair.user_emojis,
                    "assistant_emojis": pair.assistant_emojis,
                    "timestamp": pair.timestamp.isoformat(),
                    "context": pair.context,
                }
                for pair in self.conversation_pairs[:100]  # 只导出前100条示例
            ]
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[Processor] 导出到 {output_path}")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="微信聊天数据处理")
    parser.add_argument("input", help="输入的messages.json文件路径")
    parser.add_argument("--output", "-o", default="processed_chat.json", help="输出JSON文件路径")
    parser.add_argument("--import-db", action="store_true", help="导入到数据库")
    parser.add_argument("--persona-name", default=None, help="Persona名称")

    args = parser.parse_args()

    # 处理
    processor = WeChatDataProcessor(args.input)
    processor.load_messages()
    processor.extract_conversation_pairs()

    # 导出
    processor.export_to_json(args.output)

    # 导入数据库
    if args.import_db:
        processor.import_to_database(args.persona_name)

    # 打印统计
    print("\n=== 处理统计 ===")
    for key, value in processor.stats.items():
        print(f"  {key}: {value}")

    emoji_analysis = processor.analyze_emoji_usage()
    print("\n=== 我方表情包使用 ===")
    my = emoji_analysis["my_emoji_usage"]
    print(f"  使用频率: {my['frequency']} ({my['usage_rate']:.1%})")
    print(f"  表情消息: {my['emoji_messages']}, 文本消息: {my['text_messages']}")
    print(f"  常用类型: {', '.join(my['top_types'][:3])}")
    print(f"  常用场景: {', '.join(my['top_scenarios'][:3])}")

    print("\n=== 对方表情包使用 ===")
    target = emoji_analysis["target_emoji_usage"]
    print(f"  使用频率: {target['frequency']} ({target['usage_rate']:.1%})")
    print(f"  表情消息: {target['emoji_messages']}, 文本消息: {target['text_messages']}")
    print(f"  常用类型: {', '.join(target['top_types'][:3])}")
    print(f"  常用场景: {', '.join(target['top_scenarios'][:3])}")


if __name__ == "__main__":
    main()