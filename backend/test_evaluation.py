#!/usr/bin/env python3
"""
快速评估测试脚本

用于快速验证评估模块是否正常工作，无需运行完整实验。
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_response_quality():
    """测试回复质量评估"""
    from evaluation import ResponseQualityEvaluator

    print("\n=== 回复质量评估测试 ===")

    evaluator = ResponseQualityEvaluator()

    # 测试用例
    test_cases = [
        ("我喜欢吃苹果", "我爱吃苹果"),
        ("今天天气真好", "今天天气真不错"),
        ("你好吗", "你好呀"),
        ("我很开心", "哈哈太棒了"),  # 语义差异大
    ]

    print("\n| 生成 | 参考 | BLEU | 语义相似度 |")
    print("|------|------|------|------------|")

    for generated, reference in test_cases:
        bleu = evaluator.calculate_bleu(generated, reference)
        similarity = evaluator.calculate_semantic_similarity(generated, reference)
        print(f"| {generated} | {reference} | {bleu:.4f} | {similarity:.4f} |")

    print("\n✅ 回复质量评估测试通过")


def test_style_consistency():
    """测试风格一致性评估"""
    from evaluation import PersonaStyleEvaluator

    print("\n=== 风格一致性评估测试 ===")

    evaluator = PersonaStyleEvaluator()

    # 模拟 Persona 风格特征
    persona_styles = [
        {"name": "正式风格", "traits": {"formality": 0.9, "humor": 0.2, "warmth": 0.5}},
        {"name": "活泼风格", "traits": {"formality": 0.2, "humor": 0.8, "warmth": 0.7}},
        {"name": "温暖风格", "traits": {"formality": 0.4, "humor": 0.5, "warmth": 0.9}},
    ]

    # 测试回复
    test_responses = [
        "您好，请问有什么可以帮助您的？",
        "哈哈，今天真是太开心了呀！",
        "抱抱你，别难过啦，加油！",
    ]

    print("\n风格匹配度:")
    for resp in test_responses:
        print(f"\n回复: {resp}")
        for style in persona_styles:
            consistency = evaluator.calculate_style_consistency(resp, style["traits"])
            print(f"  {style['name']}: {consistency:.4f}")

    print("\n✅ 风格一致性评估测试通过")


def test_emoji_evaluation():
    """测试表情包推荐评估"""
    from evaluation import EmojiRecommendationEvaluator

    print("\n=== 表情包推荐评估测试 ===")

    emoji_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "emoji_classification.jsonl"
    )
    evaluator = EmojiRecommendationEvaluator(emoji_path if os.path.exists(emoji_path) else None)

    # 测试用例
    test_cases = [
        {"context": "今天太开心了哈哈", "emoji": {"top_category": "开心", "sub_category": "笑", "description": "哈哈大笑"}},
        {"context": "难过的一天", "emoji": {"top_category": "难过", "sub_category": "哭", "description": "伤心"}},
        {"context": "太棒了！", "emoji": {"top_category": "搞笑", "sub_category": "斗图", "description": "搞笑表情"}},
    ]

    print("\n| 情境 | 表情类别 | 适当性分数 |")
    print("|------|----------|------------|")

    for case in test_cases:
        result = evaluator.evaluate_emoji_appropriateness(case["emoji"], case["context"])
        print(f"| {case['context']} | {case['emoji']['top_category']} | {result.score:.4f} |")

    print("\n✅ 表情包推荐评估测试通过")


def test_feature_extraction():
    """测试特征提取"""
    from evaluation import PersonaStyleEvaluator

    print("\n=== 特征提取测试 ===")

    evaluator = PersonaStyleEvaluator()

    test_texts = [
        "您好，请问有什么可以帮助您的？",
        "哈哈，今天真是太开心了呀！",
        "抱抱你，别难过啦，加油！",
        "这是一个严肃的问题。",
    ]

    print("\n文本风格特征:")
    for text in test_texts:
        features = evaluator.extract_style_features(text)
        print(f"\n文本: {text}")
        print(f"  正式度: {features['formality']:.2f}")
        print(f"  幽默度: {features['humor']:.2f}")
        print(f"  温暖度: {features['warmth']:.2f}")
        print(f"  长度特征: {features['length']:.2f}")

    print("\n✅ 特征提取测试通过")


def run_all_tests():
    """运行所有测试"""
    print("="*60)
    print("数字孪生对话系统 - 评估模块测试")
    print("="*60)

    try:
        test_response_quality()
        test_style_consistency()
        test_emoji_evaluation()
        test_feature_extraction()

        print("\n" + "="*60)
        print("✅ 所有测试通过！评估模块工作正常。")
        print("="*60)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)