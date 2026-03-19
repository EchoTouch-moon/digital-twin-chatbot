"""
Emoji Behavior Analysis Service for Digital Twin Chatbot.

This service analyzes user's emoji usage patterns from chat history:
1. Calculate emoji usage frequency (high/medium/low/none)
2. Identify preferred emoji scenarios (when user sends emojis)
3. Extract emoji type preferences
4. Provide recommendations based on user's real behavior

核心理念：
- 从聊天记录中学习用户的真实表情包使用习惯
- 尊重用户习惯，不强行推荐表情包给不使用的用户
- 根据画像真实模拟用户的行为模式
"""

import json
import os
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

from sqlalchemy.orm import Session
from database import get_db, Persona, ChatHistory


class EmojiBehaviorAnalyzer:
    """
    表情包行为分析器

    从聊天记录中分析用户的表情包使用习惯，包括：
    - 使用频率
    - 使用场景
    - 类型偏好
    """

    # 表情包引用的正则模式（匹配微信导出格式）
    EMOJI_PATTERNS = [
        r'\[表情\]',  # 简单标记
        r'\[表情：([a-f0-9]{32})\]',  # MD5格式
        r'<img[^>]*emoji[^>]*>',  # HTML图片标签
        r'\[图片\]',  # 图片标记（可能是表情）
    ]

    # 场景关键词映射
    SCENARIO_KEYWORDS = {
        "开心": ["哈哈", "嘿嘿", "嘻嘻", "太好了", "开心", "高兴", "棒", "赞", "好耶"],
        "难过": ["难过", "伤心", "哭", "泪", "郁闷", "不开心", "烦"],
        "调侃": ["哈哈", "笑死", "逗", "搞笑", "奇葩", "无语"],
        "安慰": ["抱抱", "没事", "别难过", "加油", "支持"],
        "惊讶": ["哇", "天哪", "卧槽", "不是吧", "真的假的"],
        "喜欢": ["喜欢", "爱了", "想要", "好看", "可爱", "太棒了"],
        "无奈": ["算了", "没办法", "无语", "服了", "行吧"],
        "撒娇": ["哼", "嘛", "呢", "呀", "啦"],
    }

    def __init__(self, db: Session = None, emoji_classification_path: str = None):
        self.db = db or get_db()

        # 加载表情包分类数据
        self.emoji_classification = {}
        if emoji_classification_path:
            self._load_emoji_classification(emoji_classification_path)
        else:
            # 默认路径
            default_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "emoji_classification.jsonl"
            )
            if os.path.exists(default_path):
                self._load_emoji_classification(default_path)

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
                                'file_name': filename
                            }
                    except json.JSONDecodeError:
                        continue
            print(f"[EmojiBehavior] Loaded {len(self.emoji_classification)} emoji classifications")
        except Exception as e:
            print(f"[EmojiBehavior] Error loading emoji classification: {e}")

    def analyze_emoji_behavior(
        self,
        messages: List[Dict[str, str]],
        target_sender: str = None
    ) -> Dict[str, Any]:
        """
        分析消息中的表情包使用行为

        Args:
            messages: 消息列表，每条消息包含 sender, content, timestamp 等
            target_sender: 目标发送者（如果为None则分析所有消息）

        Returns:
            表情包行为分析结果
        """
        if target_sender:
            messages = [m for m in messages if m.get('sender') == target_sender]

        if not messages:
            return self._get_empty_result()

        total_messages = len(messages)
        emoji_messages = 0
        emoji_md5s = []
        scenarios = []
        types = []

        for msg in messages:
            content = msg.get('content', '')

            # 检测表情包
            has_emoji, md5_list = self._detect_emoji(content)

            if has_emoji:
                emoji_messages += 1
                emoji_md5s.extend(md5_list)

                # 分析使用场景
                scenario = self._detect_scenario(content)
                if scenario:
                    scenarios.append(scenario)

        # 计算使用率
        usage_rate = emoji_messages / total_messages if total_messages > 0 else 0

        # 获取表情包类型
        for md5 in emoji_md5s:
            if md5 in self.emoji_classification:
                emoji_info = self.emoji_classification[md5]
                types.append(emoji_info.get('top_category', '其他'))

        # 确定使用频率级别
        frequency = self._calculate_frequency(usage_rate)

        # 统计场景偏好
        scenario_prefs = self._get_top_items(scenarios, top_n=5)

        # 统计类型偏好
        type_prefs = self._get_top_items(types, top_n=5)

        return {
            "emoji_usage_frequency": frequency,
            "emoji_usage_rate": round(usage_rate, 3),
            "emoji_count": emoji_messages,
            "total_messages": total_messages,
            "emoji_scenario_prefs": scenario_prefs,
            "emoji_type_prefs": type_prefs,
            "analyzed_at": datetime.utcnow().isoformat()
        }

    def _detect_emoji(self, content: str) -> Tuple[bool, List[str]]:
        """
        检测消息中是否包含表情包

        Returns:
            (是否包含表情包, MD5列表)
        """
        md5_list = []

        # 检测MD5格式的表情引用
        pattern = r'\[表情：([a-f0-9]{32})\]'
        matches = re.findall(pattern, content)
        md5_list.extend(matches)

        # 检测其他表情标记
        for p in self.EMOJI_PATTERNS[:-1]:  # 排除最后一个图片标记
            if re.search(p, content) and not matches:
                return True, md5_list

        has_emoji = len(md5_list) > 0 or bool(re.search(r'\[表情\]', content))

        return has_emoji, md5_list

    def _detect_scenario(self, content: str) -> Optional[str]:
        """检测表情包使用的场景"""
        for scenario, keywords in self.SCENARIO_KEYWORDS.items():
            for keyword in keywords:
                if keyword in content:
                    return scenario
        return None

    def _calculate_frequency(self, usage_rate: float) -> str:
        """
        根据使用率计算频率级别

        频率标准：
        - none: 0% 不使用表情包
        - low: 0-20% 偶尔使用
        - medium: 20-50% 经常使用
        - high: 50%+ 高频使用
        """
        if usage_rate == 0:
            return "none"
        elif usage_rate < 0.2:
            return "low"
        elif usage_rate < 0.5:
            return "medium"
        else:
            return "high"

    def _get_top_items(self, items: List[str], top_n: int = 5) -> List[str]:
        """获取出现次数最多的项目"""
        if not items:
            return []
        counter = Counter(items)
        return [item for item, count in counter.most_common(top_n)]

    def _get_empty_result(self) -> Dict[str, Any]:
        """返回空结果"""
        return {
            "emoji_usage_frequency": "none",
            "emoji_usage_rate": 0.0,
            "emoji_count": 0,
            "total_messages": 0,
            "emoji_scenario_prefs": [],
            "emoji_type_prefs": [],
            "analyzed_at": datetime.utcnow().isoformat()
        }

    def should_recommend_emoji(self, persona: Persona) -> bool:
        """
        根据用户画像决定是否推荐表情包

        核心逻辑：尊重用户的真实习惯
        - 如果用户不使用表情包 -> 不推荐
        - 如果用户偶尔使用 -> 偶尔推荐
        - 如果用户经常使用 -> 经常推荐
        """
        import random

        frequency = persona.emoji_usage_frequency or "medium"

        if frequency == "none":
            # 用户不使用表情包，尊重习惯，不推荐
            return False
        elif frequency == "low":
            # 偶尔推荐 (20%概率)
            return random.random() < 0.2
        elif frequency == "medium":
            # 适度推荐 (50%概率)
            return random.random() < 0.5
        else:  # high
            # 高频推荐 (80%概率)
            return random.random() < 0.8

    def get_emoji_recommendation_context(self, persona: Persona) -> str:
        """
        获取表情包推荐的上下文信息，用于Prompt

        Returns:
            格式化的表情包使用风格描述
        """
        frequency = persona.emoji_usage_frequency or "medium"
        scenarios = persona.emoji_scenario_prefs or []
        types = persona.emoji_type_prefs or []

        parts = []

        # 频率描述
        freq_desc = {
            "none": "不使用表情包",
            "low": "偶尔使用表情包",
            "medium": "经常使用表情包",
            "high": "非常喜欢使用表情包"
        }
        parts.append(f"表情包使用习惯：{freq_desc.get(frequency, '适度使用')}")

        # 场景偏好
        if scenarios:
            parts.append(f"常用场景：{', '.join(scenarios[:3])}")

        # 类型偏好
        if types:
            parts.append(f"偏好类型：{', '.join(types[:3])}")

        return "\n".join(parts)

    def update_persona_emoji_behavior(
        self,
        persona_id: int,
        analysis_result: Dict[str, Any]
    ) -> bool:
        """
        更新Persona的表情包行为字段

        Args:
            persona_id: Persona ID
            analysis_result: 分析结果

        Returns:
            是否更新成功
        """
        persona = self.db.query(Persona).filter(Persona.id == persona_id).first()
        if not persona:
            return False

        persona.emoji_usage_frequency = analysis_result.get("emoji_usage_frequency", "medium")
        persona.emoji_usage_rate = analysis_result.get("emoji_usage_rate", 0.5)
        persona.emoji_scenario_prefs = analysis_result.get("emoji_scenario_prefs", [])
        persona.emoji_type_prefs = analysis_result.get("emoji_type_prefs", [])
        persona.updated_at = datetime.utcnow()

        self.db.commit()
        return True

    def analyze_from_chat_history(self, persona_id: int) -> Dict[str, Any]:
        """
        从已存储的聊天记录中分析表情包行为

        Args:
            persona_id: Persona ID

        Returns:
            分析结果
        """
        # 获取该persona的聊天记录
        chat_histories = self.db.query(ChatHistory).filter(
            ChatHistory.persona_id == persona_id
        ).all()

        if not chat_histories:
            return self._get_empty_result()

        # 转换为消息格式
        messages = []
        for history in chat_histories:
            # 分析assistant的回复中的表情包使用
            messages.append({
                'sender': 'assistant',
                'content': history.assistant_response,
                'timestamp': history.imported_at.isoformat() if history.imported_at else None
            })

        return self.analyze_emoji_behavior(messages, target_sender='assistant')


class EmojiBehaviorService:
    """
    表情包行为服务

    提供表情包行为分析的统一接口
    """

    def __init__(self, db: Session = None):
        self.db = db or get_db()
        self.analyzer = EmojiBehaviorAnalyzer(db=self.db)

    def analyze_and_update_persona(self, persona_id: int) -> Dict[str, Any]:
        """
        分析并更新Persona的表情包行为

        Args:
            persona_id: Persona ID

        Returns:
            分析结果
        """
        result = self.analyzer.analyze_from_chat_history(persona_id)

        if result.get('total_messages', 0) > 0:
            self.analyzer.update_persona_emoji_behavior(persona_id, result)

        return result

    def should_recommend_emoji(self, persona_id: int) -> bool:
        """
        判断是否应该推荐表情包

        Args:
            persona_id: Persona ID

        Returns:
            是否推荐
        """
        persona = self.db.query(Persona).filter(Persona.id == persona_id).first()
        if not persona:
            return False  # 默认不推荐

        return self.analyzer.should_recommend_emoji(persona)

    def get_emoji_context_for_prompt(self, persona_id: int) -> str:
        """
        获取表情包上下文用于Prompt

        Args:
            persona_id: Persona ID

        Returns:
            格式化的上下文字符串
        """
        persona = self.db.query(Persona).filter(Persona.id == persona_id).first()
        if not persona:
            return ""

        return self.analyzer.get_emoji_recommendation_context(persona)


# Singleton instance
_emoji_behavior_service = None


def get_emoji_behavior_service(db: Session = None) -> EmojiBehaviorService:
    """获取表情包行为服务单例"""
    global _emoji_behavior_service
    if _emoji_behavior_service is None:
        _emoji_behavior_service = EmojiBehaviorService(db)
    return _emoji_behavior_service


if __name__ == "__main__":
    # 测试
    from database import init_database

    init_database()

    service = get_emoji_behavior_service()

    # 测试分析
    test_messages = [
        {"sender": "user", "content": "今天天气真好啊"},
        {"sender": "assistant", "content": "是啊，心情都变好了[表情：a9aa1bdc25333fdb5d470ea03c4fc5a3]"},
        {"sender": "user", "content": "哈哈，太棒了"},
        {"sender": "assistant", "content": "开心！[表情]"},
        {"sender": "user", "content": "你真有趣"},
        {"sender": "assistant", "content": "嘿嘿，谢谢夸奖"},
        {"sender": "user", "content": "难过"},
        {"sender": "assistant", "content": "抱抱你[表情：d88a902feeb44d72e4fef3044608e27b]"},
    ]

    result = service.analyzer.analyze_emoji_behavior(test_messages, target_sender='assistant')
    print("分析结果：")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 测试推荐判断
    print("\n表情包推荐测试（10次）：")
    for i in range(10):
        # 创建模拟persona
        from database import Persona
        test_persona = Persona(
            name="测试",
            emoji_usage_frequency=result["emoji_usage_frequency"],
            emoji_usage_rate=result["emoji_usage_rate"],
            emoji_scenario_prefs=result["emoji_scenario_prefs"],
            emoji_type_prefs=result["emoji_type_prefs"]
        )
        should = service.analyzer.should_recommend_emoji(test_persona)
        print(f"  第{i+1}次: {'推荐' if should else '不推荐'}")