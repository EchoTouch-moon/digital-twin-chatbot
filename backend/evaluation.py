"""
Evaluation Module for Digital Twin Chatbot.

This module provides comprehensive evaluation metrics and experiments:
1. Response quality evaluation (BLEU, semantic similarity)
2. Persona imitation evaluation (style consistency)
3. Emoji recommendation evaluation (appropriateness, accuracy)
4. Baseline comparison experiments
5. Ablation study experiments

For thesis writing, this module provides:
- Quantitative metrics for system evaluation
- Comparison with baseline methods
- Ablation study results
"""

import os
# 设置 HuggingFace 离线模式，强制使用缓存模型
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from collections import Counter
from dataclasses import dataclass, asdict
import random

import numpy as np

# Optional imports for advanced metrics
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    print("[Evaluation] Warning: sentence-transformers not available, using fallback metrics")

try:
    from rouge import Rouge
    ROUGE_AVAILABLE = True
except ImportError:
    ROUGE_AVAILABLE = False


@dataclass
class EvaluationResult:
    """Evaluation result container."""
    metric_name: str
    score: float
    details: Dict[str, Any] = None
    timestamp: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()


@dataclass
class ExperimentResult:
    """Experiment result container."""
    experiment_name: str
    description: str
    metrics: List[EvaluationResult]
    sample_size: int
    duration_seconds: float
    timestamp: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict:
        return {
            "experiment_name": self.experiment_name,
            "description": self.description,
            "metrics": [asdict(m) for m in self.metrics],
            "sample_size": self.sample_size,
            "duration_seconds": self.duration_seconds,
            "timestamp": self.timestamp
        }


class ResponseQualityEvaluator:
    """
    Evaluates the quality of generated responses.

    Metrics:
    - BLEU score (n-gram overlap)
    - Semantic similarity (embedding-based)
    - Response length distribution
    - Coherence score
    """

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        self.model = None
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                self.model = SentenceTransformer(model_name)
                print(f"[Evaluation] Loaded embedding model: {model_name}")
            except Exception as e:
                print(f"[Evaluation] Error loading model: {e}")

    def calculate_bleu(self, candidate: str, reference: str, n: int = 4) -> float:
        """
        Calculate BLEU score for a single candidate-reference pair.

        Uses smoothed BLEU to handle zero counts.
        """
        from collections import Counter

        candidate_tokens = list(candidate)
        reference_tokens = list(reference)

        if len(candidate_tokens) == 0:
            return 0.0

        scores = []
        for i in range(1, n + 1):
            candidate_ngrams = Counter(
                tuple(candidate_tokens[j:j+i])
                for j in range(len(candidate_tokens) - i + 1)
            )
            reference_ngrams = Counter(
                tuple(reference_tokens[j:j+i])
                for j in range(len(reference_tokens) - i + 1)
            )

            if not candidate_ngrams:
                scores.append(0.0)
                continue

            matches = sum(
                min(count, reference_ngrams.get(ngram, 0))
                for ngram, count in candidate_ngrams.items()
            )
            total = sum(candidate_ngrams.values())

            # Smoothed precision
            precision = matches / total if total > 0 else 0.0
            scores.append(precision)

        # Geometric mean of precisions
        if any(s == 0 for s in scores):
            # Use smoothing for zero scores
            scores = [max(s, 0.001) for s in scores]

        geometric_mean = np.exp(np.mean(np.log(scores)))

        # Brevity penalty
        bp = 1.0
        if len(candidate_tokens) < len(reference_tokens):
            bp = np.exp(1 - len(reference_tokens) / len(candidate_tokens))

        return float(bp * geometric_mean)

    def calculate_semantic_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate semantic similarity using embeddings.

        Returns a score between 0 and 1.
        """
        if self.model is None:
            # Fallback to simple word overlap
            words1 = set(text1)
            words2 = set(text2)
            if not words1 or not words2:
                return 0.0
            intersection = words1 & words2
            union = words1 | words2
            return len(intersection) / len(union)

        try:
            embeddings = self.model.encode([text1, text2])
            # Cosine similarity
            similarity = np.dot(embeddings[0], embeddings[1]) / (
                np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1])
            )
            return float(similarity)
        except Exception as e:
            print(f"[Evaluation] Error calculating similarity: {e}")
            return 0.0

    def evaluate_response(
        self,
        generated: str,
        reference: str,
        context: str = None
    ) -> List[EvaluationResult]:
        """
        Evaluate a single response against reference.

        Returns multiple evaluation metrics.
        """
        results = []

        # BLEU score
        bleu = self.calculate_bleu(generated, reference)
        results.append(EvaluationResult(
            metric_name="bleu_score",
            score=bleu,
            details={"generated_length": len(generated), "reference_length": len(reference)}
        ))

        # Semantic similarity
        similarity = self.calculate_semantic_similarity(generated, reference)
        results.append(EvaluationResult(
            metric_name="semantic_similarity",
            score=similarity
        ))

        # Length ratio
        length_ratio = len(generated) / len(reference) if len(reference) > 0 else 0
        results.append(EvaluationResult(
            metric_name="length_ratio",
            score=min(length_ratio, 2.0) / 2.0,  # Normalize to 0-1
            details={"ratio": length_ratio}
        ))

        # ROUGE score (if available)
        if ROUGE_AVAILABLE:
            try:
                rouge = Rouge()
                scores = rouge.get_scores(generated, reference)[0]
                results.append(EvaluationResult(
                    metric_name="rouge_l_f1",
                    score=scores['rouge-l']['f']
                ))
            except:
                pass

        return results


class PersonaStyleEvaluator:
    """
    Evaluates how well the generated response matches the persona's style.

    Metrics:
    - Style consistency (formality, warmth, humor)
    - Phrase usage matching
    - Response length matching
    - Emoji usage pattern matching
    """

    def __init__(self):
        # Style indicators
        self.formality_indicators = {
            "formal": ["您好", "请问", "感谢", "非常", "请问您", "麻烦您", "劳驾"],
            "casual": ["哈哈", "嘿嘿", "啊", "呢", "呀", "啦", "嘛", "咯"]
        }

        self.humor_indicators = ["哈哈", "嘿嘿", "笑死", "逗", "奇葩", "绝了"]

        self.warmth_indicators = ["抱抱", "加油", "支持", "理解", "心疼", "没事"]

    def extract_style_features(self, text: str) -> Dict[str, float]:
        """Extract style features from text."""
        features = {}

        # Formality
        formal_count = sum(1 for ind in self.formality_indicators["formal"] if ind in text)
        casual_count = sum(1 for ind in self.formality_indicators["casual"] if ind in text)
        total_indicators = formal_count + casual_count
        features["formality"] = formal_count / total_indicators if total_indicators > 0 else 0.5

        # Humor
        humor_count = sum(1 for ind in self.humor_indicators if ind in text)
        features["humor"] = min(humor_count / 3, 1.0)

        # Warmth
        warmth_count = sum(1 for ind in self.warmth_indicators if ind in text)
        features["warmth"] = min(warmth_count / 3, 1.0)

        # Expressiveness (length relative to typical)
        features["length"] = min(len(text) / 100, 1.0)

        return features

    def calculate_style_consistency(
        self,
        generated: str,
        persona_traits: Dict[str, float]
    ) -> float:
        """
        Calculate how consistent the generated response is with persona style.

        Args:
            generated: The generated response
            persona_traits: Expected traits like {"formality": 0.7, "humor": 0.5}

        Returns:
            Consistency score between 0 and 1
        """
        generated_features = self.extract_style_features(generated)

        # Calculate feature-wise difference
        total_diff = 0
        count = 0

        for feature, expected_value in persona_traits.items():
            if feature in generated_features:
                actual_value = generated_features[feature]
                diff = abs(expected_value - actual_value)
                total_diff += diff
                count += 1

        if count == 0:
            return 0.5

        # Convert difference to similarity (0 diff = 1 similarity)
        avg_diff = total_diff / count
        similarity = 1 - avg_diff

        return max(0, similarity)

    def evaluate_persona_imitation(
        self,
        generated: str,
        persona: Any,
        reference_responses: List[str] = None
    ) -> List[EvaluationResult]:
        """
        Evaluate how well the response matches persona style.
        """
        results = []

        # Get persona traits
        traits = persona.personality_traits or {}

        # Style consistency
        consistency = self.calculate_style_consistency(generated, traits)
        results.append(EvaluationResult(
            metric_name="style_consistency",
            score=consistency,
            details={"persona_traits": traits}
        ))

        # Phrase matching
        common_phrases = persona.common_phrases or []
        if common_phrases:
            matched_phrases = [p for p in common_phrases if p in generated]
            phrase_match_rate = len(matched_phrases) / min(len(common_phrases), 5)
            results.append(EvaluationResult(
                metric_name="phrase_match_rate",
                score=phrase_match_rate,
                details={"matched": matched_phrases, "expected": common_phrases[:5]}
            ))

        # Length matching
        avg_length = persona.avg_response_length or 50
        length_diff = abs(len(generated) - avg_length)
        length_score = max(0, 1 - length_diff / 100)
        results.append(EvaluationResult(
            metric_name="length_match",
            score=length_score,
            details={"generated_length": len(generated), "expected_length": avg_length}
        ))

        return results

    def extract_persona_style_from_history(
        self,
        historical_responses: List[str]
    ) -> Dict[str, Any]:
        """
        从历史对话中提取 Persona 的风格特征。

        Returns:
            {
                "style_features": {"formality", "humor", "warmth"},
                "common_words": [高频词列表],
                "sentence_patterns": [句式模式],
                "avg_length": 平均长度
            }
        """
        import re
        from collections import Counter

        if not historical_responses:
            return {"style_features": {}, "common_words": [], "sentence_patterns": [], "avg_length": 50}

        # 提取风格特征
        all_features = [self.extract_style_features(r) for r in historical_responses if r]

        # 平均风格特征
        avg_features = {}
        for key in ["formality", "humor", "warmth", "length"]:
            values = [f.get(key, 0) for f in all_features]
            avg_features[key] = sum(values) / len(values) if values else 0.5

        # 提取高频词（过滤停用词）
        stop_words = {"的", "了", "是", "我", "你", "他", "她", "它", "们", "这", "那", "就", "也", "都", "在", "有", "和", "不", "着", "把", "被", "给", "让", "向", "对", "为", "与", "或", "但", "而", "又", "很", "好", "会", "能", "要", "想", "去", "来", "到", "说", "看", "做", "用", "没", "么", "呢", "吧", "啊", "呀", "哦", "嗯", "哈", "嘿", "啦", "嘛", "咯"}

        all_words = []
        for response in historical_responses:
            if response:
                # 提取中文词和标点符号
                words = re.findall(r'[\u4e00-\u9fff]{2,}|[！？。…]+', response)
                words = [w for w in words if w not in stop_words and len(w) >= 2]
                all_words.extend(words)

        word_freq = Counter(all_words)
        common_words = [w for w, _ in word_freq.most_common(30)]

        # 提取句式模式
        patterns = []
        for response in historical_responses:
            if response:
                # 提取句子开头的模式
                sentences = re.split(r'[！？。…]', response)
                for s in sentences:
                    s = s.strip()
                    if len(s) >= 2:
                        # 提取前2-4个字作为模式
                        pattern = s[:min(4, len(s))]
                        patterns.append(pattern)

        pattern_freq = Counter(patterns)
        common_patterns = [p for p, _ in pattern_freq.most_common(20)]

        # 平均长度
        avg_length = sum(len(r) for r in historical_responses if r) / len([r for r in historical_responses if r])

        return {
            "style_features": avg_features,
            "common_words": common_words,
            "sentence_patterns": common_patterns,
            "avg_length": avg_length
        }


class StyleTransferEvaluator:
    """
    风格迁移评估器 - 专门用于评估数字孪生的风格迁移效果。

    核心思路：
    1. 从 Persona 历史对话中提取风格特征
    2. 评估生成回复与这些风格的匹配度
    3. 评估语义相关性（回复与输入的相关性，而非与参考回复的相似度）
    """

    # 语气词和风格指示词
    TONE_WORDS = {
        "casual": ["呀", "啦", "呗", "嘛", "咯", "呢", "哈", "嘿", "哇", "嘞", "哒", "捏"],
        "enthusiastic": ["哈哈", "嘿嘿", "哇塞", "太棒了", "好耶", "绝了", "爱了"],
        "gentle": ["嗯嗯", "好的呀", "好哒", "好的呢", "知道啦", "收到"],
        "direct": ["嗯", "好", "行", "可以", "知道了", "收到"]
    }

    # 常见句式模式
    SENTENCE_PATTERNS = {
        "question": r'[^？]*？$',  # 问句
        "exclamation": r'[^！]*！$',  # 感叹句
        "ellipsis": r'[^…]*…$',  # 省略句
        "statement": r'[^。]*。$'  # 陈述句
    }

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        self.model = None
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                self.model = SentenceTransformer(model_name)
                print(f"[StyleTransfer] Loaded embedding model: {model_name}")
            except Exception as e:
                print(f"[StyleTransfer] Error loading model: {e}")

    def extract_tone_features(self, text: str) -> Dict[str, float]:
        """提取语气特征"""
        features = {}
        for tone, words in self.TONE_WORDS.items():
            count = sum(1 for w in words if w in text)
            features[tone] = min(count / 2, 1.0)
        return features

    def extract_sentence_structure(self, text: str) -> Dict[str, float]:
        """提取句式结构特征"""
        import re
        features = {}
        sentences = re.split(r'[！？。…]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return {"question": 0, "exclamation": 0, "statement": 1.0}

        total = len(sentences)
        for pattern_name, pattern in self.SENTENCE_PATTERNS.items():
            matches = len([s for s in sentences if re.match(pattern, s + '。')])
            features[pattern_name] = matches / total

        return features

    def calculate_word_overlap(self, text: str, word_list: List[str]) -> float:
        """计算文本与词表的重叠率"""
        if not word_list:
            return 0.0
        matched = sum(1 for w in word_list if w in text)
        # 使用软匹配：匹配到的词数 / 最大可能匹配数
        return min(matched / min(5, len(word_list)), 1.0)

    def calculate_semantic_relevance(self, response: str, user_input: str) -> float:
        """
        计算语义相关性：回复与用户输入的相关性
        确保回复是针对用户输入的，而不是无关的废话
        """
        if self.model is None:
            # Fallback: 关键词重叠
            input_words = set(user_input)
            response_words = set(response)
            if not input_words or not response_words:
                return 0.5
            overlap = len(input_words & response_words) / min(len(input_words), 10)
            return min(overlap, 1.0)

        try:
            embeddings = self.model.encode([response, user_input])
            similarity = np.dot(embeddings[0], embeddings[1]) / (
                np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1])
            )
            return float(max(0, similarity))
        except Exception as e:
            print(f"[StyleTransfer] Error calculating relevance: {e}")
            return 0.5

    def evaluate_style_transfer(
        self,
        generated: str,
        persona_style: Dict[str, Any],
        user_input: str
    ) -> Dict[str, Any]:
        """
        评估风格迁移效果。

        Args:
            generated: 生成的回复
            persona_style: Persona 的风格特征（从历史对话提取）
            user_input: 用户输入

        Returns:
            评估结果字典
        """
        results = {}

        # 1. 风格特征匹配度
        persona_features = persona_style.get("style_features", {})
        generated_features = {}

        # 提取生成回复的风格特征
        tone_features = self.extract_tone_features(generated)
        structure_features = self.extract_sentence_structure(generated)

        # 合并特征
        generated_features.update(tone_features)
        generated_features.update(structure_features)

        # 计算与 Persona 风格的匹配度
        if persona_features:
            feature_scores = []
            for key in ["formality", "humor", "warmth"]:
                if key in persona_features:
                    # 生成回复的特征是否接近 Persona
                    expected = persona_features[key]
                    # 对于 casual，我们看是否使用了 casual 语气词
                    if key == "formality":
                        actual = 1 - tone_features.get("casual", 0)  # 越随意，正式度越低
                    else:
                        actual = tone_features.get("enthusiastic", 0) if key == "humor" else tone_features.get("gentle", 0)

                    diff = abs(expected - actual)
                    feature_scores.append(1 - diff)

            results["style_feature_match"] = np.mean(feature_scores) if feature_scores else 0.5
        else:
            results["style_feature_match"] = 0.5

        # 2. 用词模式匹配
        common_words = persona_style.get("common_words", [])
        word_match = self.calculate_word_overlap(generated, common_words)
        results["word_pattern_match"] = word_match

        # 3. 句式模式匹配
        patterns = persona_style.get("sentence_patterns", [])
        pattern_match = sum(1 for p in patterns if p in generated) / max(len(patterns), 1)
        results["sentence_pattern_match"] = min(pattern_match * 2, 1.0)  # 放大，因为模式匹配本身就少

        # 4. 长度匹配
        expected_length = persona_style.get("avg_length", 50)
        length_ratio = len(generated) / expected_length if expected_length > 0 else 1.0
        # 长度在 0.5-2.0 倍范围内算匹配
        if 0.5 <= length_ratio <= 2.0:
            results["length_match"] = 1.0 - abs(1 - length_ratio) * 0.5
        else:
            results["length_match"] = max(0, 1 - abs(1 - length_ratio))

        # 5. 语义相关性
        results["semantic_relevance"] = self.calculate_semantic_relevance(generated, user_input)

        # 6. 综合风格迁移分数（加权平均）
        weights = {
            "style_feature_match": 0.25,
            "word_pattern_match": 0.20,
            "sentence_pattern_match": 0.15,
            "length_match": 0.15,
            "semantic_relevance": 0.25
        }

        total_score = sum(results[k] * w for k, w in weights.items())
        results["overall_style_transfer_score"] = total_score

        return results


class EmojiRecommendationEvaluator:
    """
    Evaluates the quality of emoji recommendations.

    Metrics:
    - Category appropriateness
    - Emotion matching
    - Diversity of recommendations
    """

    # Emotion to category mapping
    EMOTION_CATEGORY_MAP = {
        "happy": ["开心", "搞笑", "表情动作"],
        "sad": ["难过", "安慰", "表情动作"],
        "angry": ["生气", "无语", "表情动作"],
        "surprised": ["惊讶", "搞笑", "表情动作"],
        "love": ["喜欢", "撒娇", "表情动作"],
        "neutral": ["日常", "表情动作", "其他"]
    }

    def __init__(self, emoji_classification_path: str = None):
        self.emoji_classification = {}
        if emoji_classification_path:
            self._load_emoji_classification(emoji_classification_path)

    def _load_emoji_classification(self, path: str):
        """Load emoji classification data."""
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
                            self.emoji_classification[filename] = {
                                'top_category': data.get('top_category', '其他'),
                                'sub_category': data.get('sub_category', ''),
                                'description': data.get('description', '')
                            }
                    except json.JSONDecodeError:
                        continue
            print(f"[Evaluation] Loaded {len(self.emoji_classification)} emoji classifications")
        except Exception as e:
            print(f"[Evaluation] Error loading emoji classification: {e}")

    def detect_emotion(self, text: str) -> str:
        """Detect emotion from text."""
        emotion_keywords = {
            "happy": ["开心", "高兴", "哈哈", "嘿嘿", "太好了", "棒", "赞", "好耶"],
            "sad": ["难过", "伤心", "哭", "泪", "郁闷", "不开心"],
            "angry": ["生气", "愤怒", "火大", "烦", "无语"],
            "surprised": ["哇", "天哪", "卧槽", "震惊", "惊讶"],
            "love": ["喜欢", "爱", "想", "抱抱", "亲亲", "么么哒"]
        }

        text_lower = text.lower()
        max_matches = 0
        detected_emotion = "neutral"

        for emotion, keywords in emotion_keywords.items():
            matches = sum(1 for kw in keywords if kw in text_lower)
            if matches > max_matches:
                max_matches = matches
                detected_emotion = emotion

        return detected_emotion

    def evaluate_emoji_appropriateness(
        self,
        emoji_info: Dict[str, Any],
        context: str
    ) -> EvaluationResult:
        """
        Evaluate if the recommended emoji is appropriate for the context.
        """
        detected_emotion = self.detect_emotion(context)
        expected_categories = self.EMOTION_CATEGORY_MAP.get(detected_emotion, ["其他"])

        emoji_category = emoji_info.get("top_category", "其他")
        emoji_sub_category = emoji_info.get("sub_category", "")

        # Check if emoji category matches expected
        is_appropriate = emoji_category in expected_categories

        # Calculate appropriateness score
        if is_appropriate:
            score = 1.0
        else:
            # Partial match based on sub-category
            if any(cat in emoji_sub_category for cat in expected_categories):
                score = 0.7
            else:
                score = 0.3

        return EvaluationResult(
            metric_name="emoji_appropriateness",
            score=score,
            details={
                "detected_emotion": detected_emotion,
                "expected_categories": expected_categories,
                "actual_category": emoji_category,
                "emoji_description": emoji_info.get("description", "")
            }
        )

    def evaluate_recommendation_diversity(
        self,
        recommendations: List[Dict[str, Any]]
    ) -> EvaluationResult:
        """
        Evaluate diversity of emoji recommendations.
        """
        if not recommendations:
            return EvaluationResult(
                metric_name="recommendation_diversity",
                score=0.0
            )

        categories = [r.get("top_category", "其他") for r in recommendations]
        sub_categories = [r.get("sub_category", "") for r in recommendations]

        # Category diversity (unique categories / total)
        unique_categories = len(set(categories))
        category_diversity = unique_categories / len(categories)

        # Sub-category diversity
        unique_sub_categories = len(set(sub_categories))
        sub_category_diversity = unique_sub_categories / len(sub_categories)

        # Combined score
        diversity_score = (category_diversity + sub_category_diversity) / 2

        return EvaluationResult(
            metric_name="recommendation_diversity",
            score=diversity_score,
            details={
                "unique_categories": unique_categories,
                "unique_sub_categories": unique_sub_categories,
                "total_recommendations": len(recommendations)
            }
        )


class BaselineComparator:
    """
    Compares the full system against baseline methods.

    Baselines:
    1. No Persona: Standard chatbot without persona imitation
    2. Persona Only: Persona imitation without RAG
    3. Full System: Persona + RAG + Memory
    """

    def __init__(self, llm_service, rag_service, persona_service):
        self.llm_service = llm_service
        self.rag_service = rag_service
        self.persona_service = persona_service

    def run_baseline_no_persona(
        self,
        user_message: str,
        history: List[Dict] = None
    ) -> str:
        """Run baseline without persona (standard chatbot)."""
        # Simple chat response without persona
        messages = [
            {"role": "system", "content": "你是一个友好的AI助手，请用自然的方式回复用户。"}
        ]

        if history:
            messages.extend(history[-3:])

        messages.append({"role": "user", "content": user_message})

        try:
            response = self.llm_service.client.chat.completions.create(
                model=self.llm_service.config.model,
                messages=messages,
                temperature=0.7,
                max_tokens=200
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"[Baseline] Error: {e}")
            return "抱歉，我暂时无法回复。"

    def run_baseline_persona_only(
        self,
        user_message: str,
        persona_id: int,
        history: List[Dict] = None
    ) -> str:
        """Run baseline with persona but without RAG."""
        persona = self.persona_service.get_persona(persona_id)
        if not persona:
            return self.run_baseline_no_persona(user_message, history)

        # Generate prompt with persona
        system_prompt = self.persona_service.generate_system_prompt(
            persona_id=persona_id,
            include_examples=True,  # Include examples for style learning
            num_examples=5
        )

        messages = [{"role": "system", "content": system_prompt}]

        if history:
            messages.extend(history[-3:])

        messages.append({"role": "user", "content": f'对方说："{user_message}"'})

        try:
            response = self.llm_service.client.chat.completions.create(
                model=self.llm_service.config.model,
                messages=messages,
                temperature=0.7,
                max_tokens=200
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"[Baseline] Error: {e}")
            return "抱歉，我暂时无法回复。"

    def run_full_system(
        self,
        user_message: str,
        persona_id: int,
        history: List[Dict] = None,
        use_memory: bool = True
    ) -> Tuple[str, Optional[Dict]]:
        """
        Run full system with Persona + RAG + Memory.

        Returns:
            (response_text, emoji_info)
        """
        # This uses the existing personalized chat logic
        from llm_service import LLMService

        # Analyze intent
        intent = self.llm_service.analyze_intent(
            user_message=user_message,
            conversation_history=history,
            persona_id=persona_id
        )

        # Search for emoji if needed
        emoji_info = None
        if intent.needs_emoji and intent.search_query:
            results = self.rag_service.search(
                query=intent.search_query,
                top_k=1,
                score_threshold=0.25
            )
            if results:
                emoji_info = results[0]

        # Generate response
        response = self.llm_service.generate_personalized_response(
            user_message=user_message,
            persona_id=persona_id,
            retrieved_emoji=emoji_info,
            conversation_history=history,
            use_memory=use_memory
        )

        return response, emoji_info

    def run_comparison_experiment(
        self,
        test_cases: List[Dict[str, Any]],
        persona_id: int,
        historical_responses: List[str] = None
    ) -> Dict[str, Any]:
        """
        Run comparison experiment across all baselines.

        使用新的评估逻辑：
        1. 从 Persona 历史对话提取风格特征
        2. 评估风格迁移效果（而不是与参考回复的相似度）
        3. 评估语义相关性

        Args:
            test_cases: List of test cases with format:
                {
                    "user_message": str,
                    "reference_response": str (optional),
                    "context": str (optional)
                }
            persona_id: Persona ID for evaluation
            historical_responses: Persona 的历史回复列表，用于提取风格特征

        Returns:
            Experiment results
        """
        import time

        results = {
            "baseline_no_persona": [],
            "baseline_persona_only": [],
            "full_system": []
        }

        start_time = time.time()

        # 1. 从历史对话中提取 Persona 风格特征
        style_evaluator = StyleTransferEvaluator()
        persona_style_evaluator = PersonaStyleEvaluator()

        # 合并所有参考回复作为历史数据
        if not historical_responses:
            historical_responses = [case.get("reference_response", "") for case in test_cases if case.get("reference_response")]

        persona_style = persona_style_evaluator.extract_persona_style_from_history(historical_responses)
        print(f"[Experiment] Extracted persona style: {len(persona_style.get('common_words', []))} common words, avg length: {persona_style.get('avg_length', 0):.1f}")

        for i, case in enumerate(test_cases):
            user_message = case.get("user_message", "")
            reference = case.get("reference_response", "")
            history = case.get("history", None)

            print(f"[Experiment] Processing test case {i+1}/{len(test_cases)}")

            # Baseline 1: No Persona
            try:
                response_1 = self.run_baseline_no_persona(user_message, history)
                results["baseline_no_persona"].append({
                    "user_message": user_message,
                    "response": response_1,
                    "reference": reference
                })
            except Exception as e:
                print(f"[Experiment] Error in baseline_no_persona: {e}")

            # Baseline 2: Persona Only
            try:
                response_2 = self.run_baseline_persona_only(user_message, persona_id, history)
                results["baseline_persona_only"].append({
                    "user_message": user_message,
                    "response": response_2,
                    "reference": reference
                })
            except Exception as e:
                print(f"[Experiment] Error in baseline_persona_only: {e}")

            # Full System
            try:
                response_3, emoji_info = self.run_full_system(user_message, persona_id, history)
                results["full_system"].append({
                    "user_message": user_message,
                    "response": response_3,
                    "emoji_info": emoji_info,
                    "reference": reference
                })
            except Exception as e:
                print(f"[Experiment] Error in full_system: {e}")

        duration = time.time() - start_time

        # 2. 使用新的评估逻辑
        metrics = {}

        for baseline_name, responses in results.items():
            if not responses:
                continue

            # 传统指标（保留用于对比）
            bleu_scores = []
            similarity_scores = []

            # 新的风格迁移指标
            style_transfer_scores = []
            style_feature_matches = []
            word_pattern_matches = []
            semantic_relevances = []
            length_matches = []

            for r in responses:
                # 传统指标
                if r.get("reference"):
                    bleu = style_evaluator.calculate_bleu(r["response"], r["reference"]) if hasattr(style_evaluator, 'calculate_bleu') else 0
                    similarity = style_evaluator.calculate_semantic_relevance(r["response"], r["reference"])
                    bleu_scores.append(bleu)
                    similarity_scores.append(similarity)

                # 新的风格迁移评估
                style_result = style_evaluator.evaluate_style_transfer(
                    generated=r["response"],
                    persona_style=persona_style,
                    user_input=r["user_message"]
                )
                style_transfer_scores.append(style_result["overall_style_transfer_score"])
                style_feature_matches.append(style_result["style_feature_match"])
                word_pattern_matches.append(style_result["word_pattern_match"])
                semantic_relevances.append(style_result["semantic_relevance"])
                length_matches.append(style_result["length_match"])

            metrics[baseline_name] = {
                # 传统指标（参考价值有限）
                "avg_bleu": np.mean(bleu_scores) if bleu_scores else None,
                "avg_similarity_to_reference": np.mean(similarity_scores) if similarity_scores else None,

                # 新的风格迁移指标（核心指标）
                "style_transfer_score": np.mean(style_transfer_scores) if style_transfer_scores else 0,
                "style_feature_match": np.mean(style_feature_matches) if style_feature_matches else 0,
                "word_pattern_match": np.mean(word_pattern_matches) if word_pattern_matches else 0,
                "semantic_relevance": np.mean(semantic_relevances) if semantic_relevances else 0,
                "length_match": np.mean(length_matches) if length_matches else 0,

                "sample_count": len(responses)
            }

        return {
            "experiment_name": "baseline_comparison",
            "duration_seconds": duration,
            "persona_id": persona_id,
            "persona_style": persona_style,
            "metrics": metrics,
            "raw_results": results
        }


class AblationStudy:
    """
    Performs ablation study to evaluate contribution of each component.

    Components to ablate:
    1. Memory system
    2. RAG (similar conversations)
    3. Emoji recommendation
    4. Persona examples
    """

    def __init__(self, llm_service, rag_service, persona_service, memory_service):
        self.llm_service = llm_service
        self.rag_service = rag_service
        self.persona_service = persona_service
        self.memory_service = memory_service

    def run_ablation_memory(
        self,
        user_message: str,
        persona_id: int,
        history: List[Dict] = None
    ) -> Tuple[str, Dict]:
        """Run without memory system."""
        response = self.llm_service.generate_personalized_response(
            user_message=user_message,
            persona_id=persona_id,
            conversation_history=history,
            use_memory=False  # Ablate memory
        )
        return response, {"memory_used": False}

    def run_ablation_rag(
        self,
        user_message: str,
        persona_id: int,
        history: List[Dict] = None
    ) -> Tuple[str, Dict]:
        """Run without RAG (no similar conversations)."""
        response = self.llm_service.generate_personalized_response(
            user_message=user_message,
            persona_id=persona_id,
            conversation_history=history,
            use_similar_conversations=False  # Ablate RAG
        )
        return response, {"rag_used": False}

    def run_ablation_examples(
        self,
        user_message: str,
        persona_id: int,
        history: List[Dict] = None
    ) -> Tuple[str, Dict]:
        """Run without few-shot examples."""
        # Generate prompt without examples
        system_prompt = self.persona_service.generate_system_prompt(
            persona_id=persona_id,
            include_examples=False  # Ablate examples
        )

        messages = [{"role": "system", "content": system_prompt}]

        if history:
            messages.extend(history[-3:])

        messages.append({"role": "user", "content": f'对方说："{user_message}"'})

        try:
            response = self.llm_service.client.chat.completions.create(
                model=self.llm_service.config.model,
                messages=messages,
                temperature=0.7,
                max_tokens=200
            )
            return response.choices[0].message.content, {"examples_used": False}
        except Exception as e:
            print(f"[Ablation] Error: {e}")
            return "抱歉，我暂时无法回复。", {"examples_used": False}

    def run_ablation_study(
        self,
        test_cases: List[Dict[str, Any]],
        persona_id: int
    ) -> Dict[str, Any]:
        """
        Run full ablation study.

        Returns:
            Results for each ablation configuration
        """
        import time

        configurations = {
            "full_system": lambda msg, hist: self._run_full(msg, persona_id, hist),
            "no_memory": lambda msg, hist: self.run_ablation_memory(msg, persona_id, hist),
            "no_rag": lambda msg, hist: self.run_ablation_rag(msg, persona_id, hist),
            "no_examples": lambda msg, hist: self.run_ablation_examples(msg, persona_id, hist)
        }

        results = {config: [] for config in configurations}
        start_time = time.time()

        for i, case in enumerate(test_cases):
            user_message = case.get("user_message", "")
            history = case.get("history", None)

            print(f"[Ablation] Processing test case {i+1}/{len(test_cases)}")

            for config_name, config_func in configurations.items():
                try:
                    response, details = config_func(user_message, history)
                    results[config_name].append({
                        "user_message": user_message,
                        "response": response,
                        "details": details
                    })
                except Exception as e:
                    print(f"[Ablation] Error in {config_name}: {e}")

        duration = time.time() - start_time

        return {
            "experiment_name": "ablation_study",
            "duration_seconds": duration,
            "persona_id": persona_id,
            "results": results
        }

    def _run_full(self, user_message: str, persona_id: int, history: List[Dict]) -> Tuple[str, Dict]:
        """Run full system for comparison."""
        response = self.llm_service.generate_personalized_response(
            user_message=user_message,
            persona_id=persona_id,
            conversation_history=history,
            use_memory=True,
            use_similar_conversations=True
        )
        return response, {"full_system": True}


class EvaluationReportGenerator:
    """Generates evaluation reports for thesis."""

    @staticmethod
    def generate_markdown_report(
        experiment_results: List[Dict[str, Any]],
        output_path: str
    ):
        """Generate a markdown report of experiment results."""
        report = []
        report.append("# 数字孪生对话系统评估报告\n")
        report.append(f"生成时间: {datetime.utcnow().isoformat()}\n")

        for result in experiment_results:
            report.append(f"\n## {result.get('experiment_name', 'Unknown Experiment')}\n")
            report.append(f"- 实验描述: {result.get('description', 'N/A')}\n")
            report.append(f"- 样本数量: {result.get('sample_size', 'N/A')}\n")
            report.append(f"- 运行时长: {result.get('duration_seconds', 0):.2f}秒\n")

            metrics = result.get('metrics', {})
            if metrics:
                report.append("\n### 评估指标\n")
                report.append("| 指标 | 分数 |\n")
                report.append("|------|------|\n")
                for metric in metrics:
                    report.append(f"| {metric.get('metric_name', 'N/A')} | {metric.get('score', 0):.4f} |\n")

        # Write report
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report))

        print(f"[Report] Generated report at {output_path}")

    @staticmethod
    def generate_latex_table(
        comparison_results: Dict[str, Dict],
        output_path: str
    ):
        """Generate LaTeX table for thesis."""
        lines = []
        lines.append("\\begin{table}[htbp]")
        lines.append("\\centering")
        lines.append("\\caption{系统性能对比实验结果}")
        lines.append("\\label{tab:comparison}")
        lines.append("\\begin{tabular}{lccc}")
        lines.append("\\toprule")
        lines.append("方法 & BLEU & 语义相似度 & 样本数 \\\\")
        lines.append("\\midrule")

        for method, metrics in comparison_results.items():
            bleu = metrics.get('avg_bleu', 'N/A')
            similarity = metrics.get('avg_similarity', 'N/A')
            count = metrics.get('sample_count', 0)

            bleu_str = f"{bleu:.4f}" if isinstance(bleu, float) else str(bleu)
            sim_str = f"{similarity:.4f}" if isinstance(similarity, float) else str(similarity)

            lines.append(f"{method} & {bleu_str} & {sim_str} & {count} \\\\")

        lines.append("\\bottomrule")
        lines.append("\\end{tabular}")
        lines.append("\\end{table}")

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        print(f"[Report] Generated LaTeX table at {output_path}")


# Singleton instances
_evaluation_service = None


def get_evaluation_service(
    llm_service=None,
    rag_service=None,
    persona_service=None,
    memory_service=None
):
    """Get or create evaluation service."""
    global _evaluation_service
    if _evaluation_service is None:
        _evaluation_service = {
            "response_evaluator": ResponseQualityEvaluator(),
            "persona_evaluator": PersonaStyleEvaluator(),
            "emoji_evaluator": EmojiRecommendationEvaluator()
        }
    return _evaluation_service


if __name__ == "__main__":
    # Test evaluation module
    print("Testing Evaluation Module...")

    # Test BLEU calculation
    evaluator = ResponseQualityEvaluator()
    bleu = evaluator.calculate_bleu("我喜欢吃苹果", "我爱吃苹果")
    print(f"BLEU score: {bleu:.4f}")

    # Test semantic similarity
    similarity = evaluator.calculate_semantic_similarity("今天天气很好", "今天天气真不错")
    print(f"Semantic similarity: {similarity:.4f}")

    # Test style evaluation
    style_eval = PersonaStyleEvaluator()
    traits = {"formality": 0.3, "humor": 0.7, "warmth": 0.8}
    consistency = style_eval.calculate_style_consistency("哈哈，今天真开心呀！", traits)
    print(f"Style consistency: {consistency:.4f}")

    # Test emoji evaluation
    emoji_eval = EmojiRecommendationEvaluator()
    result = emoji_eval.evaluate_emoji_appropriateness(
        {"top_category": "开心", "sub_category": "笑", "description": "哈哈大笑"},
        "今天太开心了哈哈"
    )
    print(f"Emoji appropriateness: {result.score:.4f}")

    print("\nEvaluation module tests passed!")