"""
Chat History Processor for Digital Twin Chatbot.

This module handles parsing and processing of chat history exports
from various platforms (WeChat, QQ, etc.) to extract conversation pairs
for training the digital twin persona.
"""

import re
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from collections import Counter
import jieba
import jieba.analyse


@dataclass
class ChatMessage:
    """Represents a single chat message."""
    timestamp: datetime
    sender: str
    content: str
    message_type: str = "text"  # text, image, voice, etc.


@dataclass
class ConversationPair:
    """Represents a user-assistant conversation pair."""
    user_message: str
    assistant_response: str
    context: List[str]  # Previous messages for context
    timestamp: datetime
    topics: List[str]
    sentiment: str


class ChatHistoryProcessor:
    """
    Process chat history exports to extract training data for digital twin.
    """
    
    def __init__(self, target_person_name: str):
        """
        Initialize processor.
        
        Args:
            target_person_name: Name of the person to mimic (the digital twin)
        """
        self.target_person = target_person_name
        self.conversation_pairs: List[ConversationPair] = []
        self.all_messages: List[ChatMessage] = []
        
    def parse_wechat_export(self, file_path: str) -> List[ChatMessage]:
        """
        Parse WeChat chat export file.
        
        Supports formats:
        - Plain text exports
        - HTML exports
        - JSON exports (from backup tools)
        """
        messages = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Try to detect format
        if content.strip().startswith('{'):
            # JSON format
            messages = self._parse_wechat_json(content)
        elif '<html>' in content.lower():
            # HTML format
            messages = self._parse_wechat_html(content)
        else:
            # Plain text format
            messages = self._parse_wechat_text(content)
        
        self.all_messages.extend(messages)
        return messages
    
    def _parse_wechat_text(self, content: str) -> List[ChatMessage]:
        """Parse WeChat plain text export."""
        messages = []
        
        # Common WeChat text patterns
        # Pattern 1: "2023-01-15 14:30:45 张三: 消息内容"
        # Pattern 2: "张三 2023/1/15 14:30 消息内容"
        
        patterns = [
            r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+([^:]+):\s*(.+)',
            r'(\d{4}/\d{1,2}/\d{1,2}\s+\d{2}:\d{2})\s+([^:]+):\s*(.+)',
        ]
        
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            for pattern in patterns:
                match = re.match(pattern, line)
                if match:
                    time_str, sender, content_text = match.groups()
                    try:
                        timestamp = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        try:
                            timestamp = datetime.strptime(time_str, '%Y/%m/%d %H:%M')
                        except ValueError:
                            continue
                    
                    messages.append(ChatMessage(
                        timestamp=timestamp,
                        sender=sender.strip(),
                        content=content_text.strip()
                    ))
                    break
        
        return messages
    
    def _parse_wechat_json(self, content: str) -> List[ChatMessage]:
        """Parse WeChat JSON export format."""
        messages = []
        
        try:
            data = json.loads(content)
            # Handle different JSON structures from various export tools
            if isinstance(data, list):
                for item in data:
                    msg = self._extract_message_from_json(item)
                    if msg:
                        messages.append(msg)
            elif isinstance(data, dict):
                # Try common keys
                msg_list = data.get('messages', data.get('chat', []))
                for item in msg_list:
                    msg = self._extract_message_from_json(item)
                    if msg:
                        messages.append(msg)
        except json.JSONDecodeError:
            pass
        
        return messages
    
    def _extract_message_from_json(self, item: dict) -> Optional[ChatMessage]:
        """Extract message from JSON item."""
        try:
            timestamp_str = item.get('time', item.get('timestamp', item.get('createTime')))
            if isinstance(timestamp_str, (int, float)):
                timestamp = datetime.fromtimestamp(timestamp_str)
            else:
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            
            sender = item.get('sender', item.get('from', item.get('nickName')))
            content = item.get('content', item.get('msg', item.get('message')))
            
            if sender and content:
                return ChatMessage(
                    timestamp=timestamp,
                    sender=str(sender),
                    content=str(content)
                )
        except (ValueError, TypeError):
            pass
        
        return None
    
    def _parse_wechat_html(self, content: str) -> List[ChatMessage]:
        """Parse WeChat HTML export (basic implementation)."""
        messages = []
        
        # Simple regex-based HTML parsing
        # Pattern: <div class="msg">...<span class="sender">Name</span>...<span class="content">Message</span>...</div>
        pattern = r'<div[^>]*class=["\']msg["\'][^>]*>.*?<span[^>]*class=["\']sender["\'][^>]*>(.*?)</span>.*?<span[^>]*class=["\']content["\'][^>]*>(.*?)</span>.*?</div>'
        
        for match in re.finditer(pattern, content, re.DOTALL | re.IGNORECASE):
            sender = re.sub(r'<[^>]+>', '', match.group(1)).strip()
            content = re.sub(r'<[^>]+>', '', match.group(2)).strip()
            
            if sender and content:
                messages.append(ChatMessage(
                    timestamp=datetime.now(),  # HTML may not have timestamps
                    sender=sender,
                    content=content
                ))
        
        return messages
    
    def extract_conversation_pairs(self, context_window: int = 3) -> List[ConversationPair]:
        """
        Extract user-assistant conversation pairs from messages.
        
        Args:
            context_window: Number of previous messages to include as context
        """
        pairs = []
        
        # Sort messages by timestamp
        sorted_messages = sorted(self.all_messages, key=lambda m: m.timestamp)
        
        for i, msg in enumerate(sorted_messages):
            # Check if this is a message from the target person
            if self.target_person in msg.sender:
                # Find the previous message (user message)
                if i > 0:
                    prev_msg = sorted_messages[i - 1]
                    
                    # Get context (previous messages before user message)
                    context_start = max(0, i - context_window - 1)
                    context = [
                        f"{m.sender}: {m.content}"
                        for m in sorted_messages[context_start:i-1]
                    ]
                    
                    # Analyze topics and sentiment
                    topics = self._extract_topics(prev_msg.content)
                    sentiment = self._analyze_sentiment(prev_msg.content)
                    
                    pair = ConversationPair(
                        user_message=prev_msg.content,
                        assistant_response=msg.content,
                        context=context,
                        timestamp=msg.timestamp,
                        topics=topics,
                        sentiment=sentiment
                    )
                    pairs.append(pair)
        
        self.conversation_pairs.extend(pairs)
        return pairs
    
    def _extract_topics(self, text: str, top_k: int = 3) -> List[str]:
        """Extract key topics from text using jieba."""
        keywords = jieba.analyse.extract_tags(text, topK=top_k, withWeight=False)
        return keywords
    
    def _analyze_sentiment(self, text: str) -> str:
        """
        Simple sentiment analysis based on keywords.
        Returns: happy, sad, angry, surprised, neutral
        """
        positive_words = ['开心', '高兴', '快乐', '棒', '赞', '好', '喜欢', '爱', '哈哈', '嘿嘿']
        negative_words = ['难过', '伤心', '讨厌', '恨', '生气', '烦', '累', '郁闷']
        angry_words = ['愤怒', '火大', '滚', '骂', '气死', '妈的']
        surprised_words = ['惊讶', '震惊', '哇', '天啊', 'omg', '哦豁']
        
        text_lower = text.lower()
        
        if any(w in text_lower for w in angry_words):
            return 'angry'
        elif any(w in text_lower for w in surprised_words):
            return 'surprised'
        elif any(w in text_lower for w in negative_words):
            return 'sad'
        elif any(w in text_lower for w in positive_words):
            return 'happy'
        else:
            return 'neutral'
    
    def analyze_personality(self) -> Dict[str, Any]:
        """
        Analyze personality traits from conversation history.
        """
        if not self.conversation_pairs:
            return {}
        
        # Collect all responses from target person
        responses = [pair.assistant_response for pair in self.conversation_pairs]
        all_text = ' '.join(responses)
        
        # Calculate metrics
        avg_length = sum(len(r) for r in responses) / len(responses)
        
        # Common phrases (2-4 word combinations)
        phrases = []
        for text in responses:
            words = list(jieba.cut(text))
            for i in range(len(words) - 1):
                phrases.append(words[i] + words[i+1])
        
        common_phrases = Counter(phrases).most_common(10)
        
        # Response style analysis
        question_ratio = sum(1 for r in responses if '?' in r or '？' in r) / len(responses)
        exclamation_ratio = sum(1 for r in responses if '!' in r or '！' in r) / len(responses)
        
        # Emoji/表情 usage
        emoji_count = sum(1 for r in responses if any(ord(c) > 127 for c in r))
        emoji_ratio = emoji_count / len(responses)
        
        # Formality estimation (based on punctuation and sentence structure)
        formal_markers = ['您', '请', '谢谢', '抱歉', '对不起']
        casual_markers = ['你', '哈', '啦', '呢', '吧']
        
        formal_count = sum(all_text.count(m) for m in formal_markers)
        casual_count = sum(all_text.count(m) for m in casual_markers)
        
        formality_score = formal_count / (formal_count + casual_count + 1)
        
        return {
            'avg_response_length': int(avg_length),
            'response_count': len(responses),
            'common_phrases': [phrase for phrase, count in common_phrases],
            'question_ratio': round(question_ratio, 2),
            'exclamation_ratio': round(exclamation_ratio, 2),
            'emoji_usage_ratio': round(emoji_ratio, 2),
            'formality_score': round(formality_score, 2),
            'response_style': 'formal' if formality_score > 0.5 else 'casual',
            'humor_indicator': exclamation_ratio > 0.3,
        }
    
    def get_training_examples(self, n: int = 10) -> List[Dict[str, str]]:
        """
        Get top N conversation pairs as training examples for few-shot learning.
        """
        # Sort by diversity of topics
        examples = []
        seen_topics = set()
        
        for pair in sorted(self.conversation_pairs, key=lambda p: p.timestamp, reverse=True):
            topic_key = tuple(sorted(pair.topics[:2]))
            if topic_key not in seen_topics or len(examples) < n:
                examples.append({
                    'input': pair.user_message,
                    'output': pair.assistant_response,
                    'context': '\n'.join(pair.context) if pair.context else ''
                })
                seen_topics.add(topic_key)
            
            if len(examples) >= n:
                break
        
        return examples
    
    def export_to_json(self, output_path: str):
        """Export processed data to JSON file."""
        data = {
            'target_person': self.target_person,
            'total_messages': len(self.all_messages),
            'conversation_pairs': [
                {
                    'user_message': pair.user_message,
                    'assistant_response': pair.assistant_response,
                    'context': pair.context,
                    'timestamp': pair.timestamp.isoformat(),
                    'topics': pair.topics,
                    'sentiment': pair.sentiment
                }
                for pair in self.conversation_pairs
            ],
            'personality_analysis': self.analyze_personality()
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"[ChatProcessor] Exported {len(self.conversation_pairs)} pairs to {output_path}")


# Convenience function
def process_chat_history(file_path: str, target_person: str) -> Tuple[List[ConversationPair], Dict[str, Any]]:
    """
    Process a chat history file and return conversation pairs and personality analysis.
    
    Args:
        file_path: Path to chat export file
        target_person: Name of the person to mimic
    
    Returns:
        Tuple of (conversation_pairs, personality_analysis)
    """
    processor = ChatHistoryProcessor(target_person)
    processor.parse_wechat_export(file_path)
    pairs = processor.extract_conversation_pairs()
    personality = processor.analyze_personality()
    
    return pairs, personality


if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python chat_history_processor.py <chat_file> <target_person_name>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    target_person = sys.argv[2]
    
    processor = ChatHistoryProcessor(target_person)
    processor.parse_wechat_export(file_path)
    pairs = processor.extract_conversation_pairs()
    personality = processor.analyze_personality()
    
    print(f"\nProcessed {len(pairs)} conversation pairs")
    print(f"\nPersonality Analysis:")
    for key, value in personality.items():
        print(f"  {key}: {value}")
    
    # Export
    processor.export_to_json(f"{target_person}_processed.json")
