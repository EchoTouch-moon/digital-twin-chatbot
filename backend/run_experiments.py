#!/usr/bin/env python3
"""
实验运行脚本

用于毕业论文的评估实验，包括：
1. Baseline 对比实验
2. 消融实验
3. 风格迁移效果评估
4. 表情包推荐评估

使用方法：
    python run_experiments.py --persona_id 5 --output_dir ./results

输出：
    - experiment_results.json: 完整实验结果
    - comparison_table.tex: LaTeX 格式的对比表格（可直接用于论文）
    - experiment_report.md: Markdown 格式的报告
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Any, Optional

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

# 加载环境变量
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, '.env'), override=True)

from database import init_database, get_db, Persona, ChatHistory
from llm_service import LLMService, LLMConfig
from rag_service import RAGService
from persona_service import get_persona_service
from memory_service import get_memory_service


class ExperimentRunner:
    """实验运行器"""

    def __init__(self, output_dir: str = "./evaluation_results"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

        # 初始化服务
        self._init_services()

    def _init_services(self):
        """初始化所需服务"""
        print("[实验] 正在初始化服务...")

        # 初始化数据库
        init_database()

        # 初始化 LLM 服务
        from dotenv import dotenv_values
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
        env_config = dotenv_values(config_path)

        llm_config = LLMConfig(
            api_key=env_config.get("OPENAI_API_KEY", ""),
            base_url=env_config.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=env_config.get("OPENAI_MODEL", "gpt-3.5-turbo"),
            temperature=0.7,
            max_tokens=500
        )
        self.llm_service = LLMService(llm_config)
        print("[实验] LLM 服务初始化完成")

        # 初始化 RAG 服务
        self.rag_service = RAGService(
            jsonl_path=os.path.join(PROJECT_ROOT, "emoji_classification.jsonl"),
            model_name="paraphrase-multilingual-MiniLM-L12-v2",
            embedding_dim=384
        )
        self.rag_service.initialize()
        print("[实验] RAG 服务初始化完成")

        # 初始化其他服务
        self.persona_service = get_persona_service()
        self.memory_service = get_memory_service()

        print("[实验] 所有服务初始化完成")

    def get_test_cases(self, persona_id: int, limit: int = 20) -> List[Dict]:
        """获取测试用例"""
        db = get_db()
        chat_histories = db.query(ChatHistory).filter(
            ChatHistory.persona_id == persona_id
        ).limit(limit).all()

        return [
            {
                "user_message": h.user_message,
                "reference_response": h.assistant_response
            }
            for h in chat_histories
        ]

    def run_baseline_comparison(
        self,
        persona_id: int,
        test_cases: List[Dict]
    ) -> Dict[str, Any]:
        """
        运行 Baseline 对比实验

        对比三种方法：
        1. Baseline (No Persona): 普通聊天机器人
        2. Persona Only: 仅使用 Persona，不使用 RAG
        3. Full System: 完整系统 (Persona + RAG + Memory)
        """
        from evaluation import BaselineComparator, ResponseQualityEvaluator

        print(f"\n[实验] 开始 Baseline 对比实验，样本数: {len(test_cases)}")

        comparator = BaselineComparator(
            self.llm_service, self.rag_service, self.persona_service
        )

        start_time = time.time()
        results = comparator.run_comparison_experiment(test_cases, persona_id)
        duration = time.time() - start_time

        print(f"[实验] Baseline 对比实验完成，耗时: {duration:.2f}秒")

        return results

    def run_ablation_study(
        self,
        persona_id: int,
        test_cases: List[Dict]
    ) -> Dict[str, Any]:
        """
        运行消融实验

        分别移除以下组件评估其贡献：
        1. Memory System
        2. RAG (Similar Conversations)
        3. Few-shot Examples
        """
        from evaluation import AblationStudy

        print(f"\n[实验] 开始消融实验，样本数: {len(test_cases)}")

        ablation = AblationStudy(
            self.llm_service, self.rag_service,
            self.persona_service, self.memory_service
        )

        start_time = time.time()
        results = ablation.run_ablation_study(test_cases, persona_id)
        duration = time.time() - start_time

        print(f"[实验] 消融实验完成，耗时: {duration:.2f}秒")

        return results

    def run_style_evaluation(
        self,
        persona_id: int,
        test_cases: List[Dict]
    ) -> Dict[str, Any]:
        """
        运行风格迁移效果评估

        评估生成回复与 Persona 风格的一致性
        """
        from evaluation import PersonaStyleEvaluator

        print(f"\n[实验] 开始风格迁移评估，样本数: {len(test_cases)}")

        evaluator = PersonaStyleEvaluator()
        persona = self.persona_service.get_persona(persona_id)

        results = []
        for i, case in enumerate(test_cases):
            # 生成回复
            response = self.llm_service.generate_personalized_response(
                user_message=case["user_message"],
                persona_id=persona_id,
                conversation_history=None
            )

            # 评估风格一致性
            style_results = evaluator.evaluate_persona_imitation(
                generated=response,
                persona=persona
            )

            results.append({
                "user_message": case["user_message"],
                "response": response,
                "style_scores": {r.metric_name: r.score for r in style_results}
            })

            if (i + 1) % 5 == 0:
                print(f"[实验] 已处理 {i+1}/{len(test_cases)} 个样本")

        # 计算平均分数
        avg_scores = {}
        for r in results:
            for metric, score in r["style_scores"].items():
                if metric not in avg_scores:
                    avg_scores[metric] = []
                avg_scores[metric].append(score)

        final_scores = {k: sum(v)/len(v) for k, v in avg_scores.items()}

        print(f"[实验] 风格迁移评估完成")

        return {
            "avg_scores": final_scores,
            "sample_count": len(results),
            "details": results
        }

    def run_emoji_evaluation(
        self,
        persona_id: int,
        test_cases: List[Dict]
    ) -> Dict[str, Any]:
        """
        运行表情包推荐评估

        评估表情包推荐的准确性和适当性
        """
        from evaluation import EmojiRecommendationEvaluator

        print(f"\n[实验] 开始表情包推荐评估，样本数: {len(test_cases)}")

        emoji_path = os.path.join(PROJECT_ROOT, "emoji_classification.jsonl")
        evaluator = EmojiRecommendationEvaluator(emoji_path)

        results = []
        appropriate_count = 0

        for i, case in enumerate(test_cases):
            # 分析意图
            intent = self.llm_service.analyze_intent(
                user_message=case["user_message"],
                persona_id=persona_id
            )

            emoji_info = None
            if intent.needs_emoji:
                # 搜索表情包
                emoji_results = self.rag_service.search(
                    query=intent.search_query,
                    top_k=1,
                    score_threshold=0.25
                )
                if emoji_results:
                    emoji_info = emoji_results[0]

                    # 评估适当性
                    appropriateness = evaluator.evaluate_emoji_appropriateness(
                        emoji_info,
                        case["user_message"]
                    )

                    results.append({
                        "user_message": case["user_message"],
                        "emoji_info": emoji_info,
                        "appropriateness_score": appropriateness.score,
                        "details": appropriateness.details
                    })

                    if appropriateness.score >= 0.7:
                        appropriate_count += 1

        # 计算准确率
        accuracy = appropriate_count / len(results) if results else 0

        print(f"[实验] 表情包推荐评估完成，准确率: {accuracy:.2%}")

        return {
            "total_recommendations": len(results),
            "appropriate_count": appropriate_count,
            "accuracy": accuracy,
            "details": results
        }

    def run_all_experiments(
        self,
        persona_id: int,
        num_samples: int = 20,
        include_ablation: bool = True
    ) -> Dict[str, Any]:
        """运行所有实验"""
        print("\n" + "="*60)
        print("开始运行完整评估实验")
        print("="*60)

        # 获取 Persona 信息
        persona = self.persona_service.get_persona(persona_id)
        if not persona:
            raise ValueError(f"Persona with ID {persona_id} not found")

        print(f"\n[实验] Persona: {persona.name}")
        print(f"[实验] 描述: {persona.description}")

        # 获取测试用例
        test_cases = self.get_test_cases(persona_id, num_samples)
        if not test_cases:
            raise ValueError(f"No test cases found for persona {persona_id}")

        print(f"[实验] 测试样本数: {len(test_cases)}")

        # 运行各项实验
        all_results = {
            "experiment_info": {
                "persona_id": persona_id,
                "persona_name": persona.name,
                "num_samples": len(test_cases),
                "timestamp": datetime.utcnow().isoformat()
            }
        }

        # 1. Baseline 对比实验
        all_results["baseline_comparison"] = self.run_baseline_comparison(
            persona_id, test_cases
        )

        # 2. 消融实验
        if include_ablation:
            all_results["ablation_study"] = self.run_ablation_study(
                persona_id, test_cases[:min(10, len(test_cases))]
            )

        # 3. 风格迁移评估
        all_results["style_evaluation"] = self.run_style_evaluation(
            persona_id, test_cases[:min(15, len(test_cases))]
        )

        # 4. 表情包推荐评估
        all_results["emoji_evaluation"] = self.run_emoji_evaluation(
            persona_id, test_cases
        )

        return all_results

    def save_results(self, results: Dict[str, Any], filename: str = None):
        """保存实验结果"""
        if filename is None:
            filename = f"experiment_{results['experiment_info']['persona_id']}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"

        output_path = os.path.join(self.output_dir, filename)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)

        print(f"\n[实验] 结果已保存到: {output_path}")
        return output_path

    def generate_latex_table(self, results: Dict[str, Any]):
        """生成 LaTeX 表格用于论文"""
        if "baseline_comparison" in results:
            metrics = results["baseline_comparison"].get("metrics", {})

            latex_content = """\\begin{table}[htbp]
\\centering
\\caption{风格迁移效果对比实验结果}
\\label{tab:style_transfer_comparison}
\\begin{tabular}{lccccc}
\\toprule
方法 & 风格迁移分数 & 风格特征匹配 & 用词模式匹配 & 语义相关性 & 样本数 \\\\
\\midrule
"""
            for method, m in metrics.items():
                style_score = m.get("style_transfer_score", 0)
                feature_match = m.get("style_feature_match", 0)
                word_match = m.get("word_pattern_match", 0)
                relevance = m.get("semantic_relevance", 0)
                count = m.get("sample_count", 0)

                # 简化方法名
                method_display = method.replace("baseline_", "").replace("_", " ").title()
                if method == "baseline_no_persona":
                    method_display = "No Persona"
                elif method == "baseline_persona_only":
                    method_display = "Persona Only"
                elif method == "full_system":
                    method_display = "Full System"

                latex_content += f"{method_display} & {style_score:.4f} & {feature_match:.4f} & {word_match:.4f} & {relevance:.4f} & {count} \\\\\n"

            latex_content += """\\bottomrule
\\end{tabular}
\\end{table}
"""
            latex_path = os.path.join(self.output_dir, "comparison_table.tex")
            with open(latex_path, 'w', encoding='utf-8') as f:
                f.write(latex_content)

            print(f"[Report] Generated LaTeX table at {latex_path}")
            return latex_path
        return None

    def generate_summary_report(self, results: Dict[str, Any]):
        """生成摘要报告"""
        report = []
        report.append("# 数字孪生对话系统评估报告\n")
        report.append(f"生成时间: {results['experiment_info']['timestamp']}\n")
        report.append(f"Persona: {results['experiment_info']['persona_name']}\n")
        report.append(f"样本数: {results['experiment_info']['num_samples']}\n")

        # Baseline 对比结果 - 新的风格迁移指标
        if "baseline_comparison" in results:
            report.append("\n## 风格迁移效果对比实验结果\n")
            report.append("\n### 核心指标（风格迁移评估）\n")
            report.append("| 方法 | 风格迁移分数 | 风格特征匹配 | 用词模式匹配 | 语义相关性 | 长度匹配 |\n")
            report.append("|------|-------------|-------------|-------------|-----------|----------|\n")
            metrics = results["baseline_comparison"].get("metrics", {})
            for method, m in metrics.items():
                style_score = m.get("style_transfer_score", 0)
                feature_match = m.get("style_feature_match", 0)
                word_match = m.get("word_pattern_match", 0)
                relevance = m.get("semantic_relevance", 0)
                length_match = m.get("length_match", 0)
                report.append(f"| {method} | {style_score:.4f} | {feature_match:.4f} | {word_match:.4f} | {relevance:.4f} | {length_match:.4f} |\n")

            # 传统指标（参考）
            report.append("\n### 参考指标（与参考回复的相似度）\n")
            report.append("| 方法 | BLEU | 与参考相似度 | 样本数 |\n")
            report.append("|------|------|-------------|--------|\n")
            for method, m in metrics.items():
                bleu = m.get("avg_bleu")
                sim = m.get("avg_similarity_to_reference")
                count = m.get("sample_count", 0)
                bleu_str = f"{bleu:.4f}" if bleu is not None else "N/A"
                sim_str = f"{sim:.4f}" if sim is not None else "N/A"
                report.append(f"| {method} | {bleu_str} | {sim_str} | {count} |\n")

            # 指标说明
            report.append("\n### 指标说明\n")
            report.append("- **风格迁移分数**: 综合评估回复风格与 Persona 的匹配程度（越高越好）\n")
            report.append("- **风格特征匹配**: 语气、正式度等风格特征的匹配度\n")
            report.append("- **用词模式匹配**: 是否使用了 Persona 常用的词汇\n")
            report.append("- **语义相关性**: 回复与用户输入的语义相关程度\n")
            report.append("- **长度匹配**: 回复长度与 Persona 平均长度的匹配度\n")
            report.append("\n**注意**: BLEU 和与参考相似度指标不适合评估风格迁移效果，仅供参考。\n")

        # 风格评估结果
        if "style_evaluation" in results:
            report.append("\n## 风格迁移评估结果\n")
            avg_scores = results["style_evaluation"].get("avg_scores", {})
            report.append("| 指标 | 分数 |\n")
            report.append("|------|------|\n")
            for metric, score in avg_scores.items():
                report.append(f"| {metric} | {score:.4f} |\n")

        # 表情包评估结果
        if "emoji_evaluation" in results:
            report.append("\n## 表情包推荐评估结果\n")
            emoji_eval = results["emoji_evaluation"]
            report.append(f"- 推荐总数: {emoji_eval['total_recommendations']}\n")
            report.append(f"- 适当推荐数: {emoji_eval['appropriate_count']}\n")
            report.append(f"- 准确率: {emoji_eval['accuracy']:.2%}\n")

        # 保存报告
        report_path = os.path.join(self.output_dir, "experiment_report.md")
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report))

        print(f"[实验] 报告已保存到: {report_path}")
        return report_path


def main():
    parser = argparse.ArgumentParser(description="运行数字孪生对话系统评估实验")
    parser.add_argument(
        "--persona_id",
        type=int,
        required=True,
        help="要评估的 Persona ID"
    )
    parser.add_argument(
        "--num_samples",
        type=int,
        default=20,
        help="测试样本数量 (默认: 20)"
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="./evaluation_results",
        help="输出目录 (默认: ./evaluation_results)"
    )
    parser.add_argument(
        "--no_ablation",
        action="store_true",
        help="跳过消融实验"
    )

    args = parser.parse_args()

    # 创建实验运行器
    runner = ExperimentRunner(output_dir=args.output_dir)

    # 运行实验
    results = runner.run_all_experiments(
        persona_id=args.persona_id,
        num_samples=args.num_samples,
        include_ablation=not args.no_ablation
    )

    # 保存结果
    runner.save_results(results)

    # 生成 LaTeX 表格
    runner.generate_latex_table(results)

    # 生成摘要报告
    runner.generate_summary_report(results)

    print("\n" + "="*60)
    print("实验完成！")
    print("="*60)

    # 打印摘要 - 使用新的风格迁移指标
    if "baseline_comparison" in results:
        metrics = results["baseline_comparison"].get("metrics", {})
        print("\n[风格迁移效果对比结果]")
        print("-" * 60)
        for method, m in metrics.items():
            print(f"\n  {method}:")
            print(f"    风格迁移分数: {m.get('style_transfer_score', 0):.4f}")
            print(f"    风格特征匹配: {m.get('style_feature_match', 0):.4f}")
            print(f"    用词模式匹配: {m.get('word_pattern_match', 0):.4f}")
            print(f"    语义相关性:   {m.get('semantic_relevance', 0):.4f}")
            print(f"    长度匹配:     {m.get('length_match', 0):.4f}")


if __name__ == "__main__":
    main()