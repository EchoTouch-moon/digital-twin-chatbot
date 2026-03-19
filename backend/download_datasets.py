"""
数据集下载脚本

下载用于评估和测试的中文对话数据集：
1. LCCC - 大规模中文对话数据集（评估基准）
2. CPED - 中文个性化情感对话数据集（风格迁移评估）
3. KdConv - 知识驱动对话数据集（记忆系统测试）

使用方法：
    python download_datasets.py --dataset lccc
    python download_datasets.py --dataset cped
    python download_datasets.py --dataset all
"""

import os
import json
import argparse
from pathlib import Path
from typing import Dict, List, Any
import requests
from tqdm import tqdm

# 数据集保存目录
DATASET_DIR = Path(__file__).parent.parent / "datasets"
DATASET_DIR.mkdir(exist_ok=True)


def download_file(url: str, save_path: Path, chunk_size: int = 8192) -> bool:
    """下载文件，支持进度条"""
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))

        with open(save_path, 'wb') as f:
            with tqdm(total=total_size, unit='B', unit_scale=True, desc=save_path.name) as pbar:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    f.write(chunk)
                    pbar.update(len(chunk))

        return True
    except Exception as e:
        print(f"[ERROR] 下载失败: {e}")
        return False


def download_lccc():
    """
    下载 LCCC 数据集

    LCCC (Large-scale Chinese Conversation Dataset) 是一个大规模中文对话数据集
    包含约1200万对话，适合作为评估基准

    数据来源: https://github.com/thu-coai/LCCC
    """
    print("\n" + "="*60)
    print("下载 LCCC 数据集")
    print("="*60)

    lccc_dir = DATASET_DIR / "LCCC"
    lccc_dir.mkdir(exist_ok=True)

    # 尝试使用 Hugging Face datasets 库
    try:
        from datasets import load_dataset
        print("[INFO] 使用 Hugging Face datasets 库下载...")

        # 尝试多个可能的数据集名称
        dataset_names = [
            "thu-coai/LCCC",
            "LCCC",
            "sJun/lccc",  # 修正名称
        ]

        dataset = None
        for name in dataset_names:
            try:
                print(f"[INFO] 尝试: {name}")
                dataset = load_dataset(name)
                print(f"[INFO] 成功加载: {name}")
                break
            except Exception as e:
                print(f"[INFO] {name} 不可用: {str(e)[:50]}")
                continue

        if dataset is None:
            raise Exception("所有数据源均不可用")

        # 保存为 JSON 格式
        output_file = lccc_dir / "lccc_data.json"
        data = []

        for split in dataset:
            print(f"[INFO] 处理 {split}...")
            for item in tqdm(dataset[split], desc=f"处理 {split}"):
                data.append(item)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[SUCCESS] LCCC 数据集已保存到: {output_file}")
        print(f"[INFO] 总样本数: {len(data)}")

        return True

    except ImportError:
        print("[WARN] 未安装 datasets 库，尝试手动下载...")
        print("[INFO] 请运行: pip install datasets")

    except Exception as e:
        print(f"[ERROR] Hugging Face 下载失败: {e}")

    # 备选方案：从 GitHub 下载
    print("[INFO] 请手动从以下地址下载 LCCC 数据集：")
    print("       https://github.com/thu-coai/LCCC")
    print("       下载后解压到:", lccc_dir)

    return False


def download_cped():
    """
    下载 CPED 数据集

    CPED (Chinese Personalized Emotional Dialogue) 是中文个性化情感对话数据集
    包含 25 种人格标签和 6 种情感标签，非常适合风格迁移评估

    数据来源: https://github.com/scutcyr/CPED
    """
    print("\n" + "="*60)
    print("下载 CPED 数据集")
    print("="*60)

    cped_dir = DATASET_DIR / "CPED"
    cped_dir.mkdir(exist_ok=True)

    try:
        from datasets import load_dataset
        print("[INFO] 使用 Hugging Face datasets 库下载...")

        # 尝试从 Hugging Face 下载
        try:
            dataset = load_dataset("s Jun/CPED", trust_remote_code=True)
        except:
            print("[INFO] 尝试从其他来源下载...")
            # CPED 可能在其他名称下
            dataset = load_dataset("imvladikon/CPED", trust_remote_code=True)

        output_file = cped_dir / "cped_data.json"
        data = []

        for split in dataset:
            for item in tqdm(dataset[split], desc=f"处理 {split}"):
                data.append(item)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[SUCCESS] CPED 数据集已保存到: {output_file}")

        return True

    except Exception as e:
        print(f"[ERROR] 下载失败: {e}")

    # 手动下载指南
    print("\n[INFO] 请手动从以下地址下载 CPED 数据集：")
    print("       GitHub: https://github.com/scutcyr/CPED")
    print("       百度网盘: 见 GitHub README")
    print("       下载后解压到:", cped_dir)

    return False


def download_kdconv():
    """
    下载 KdConv 数据集

    KdConv 是知识驱动的中文多轮对话数据集
    包含 4.5 万对话，适合测试记忆系统

    数据来源: https://github.com/thu-coai/KdConv
    """
    print("\n" + "="*60)
    print("下载 KdConv 数据集")
    print("="*60)

    kdconv_dir = DATASET_DIR / "KdConv"
    kdconv_dir.mkdir(exist_ok=True)

    try:
        from datasets import load_dataset
        print("[INFO] 使用 Hugging Face datasets 库下载...")

        dataset = load_dataset("thu-coai/KdConv", trust_remote_code=True)

        # 处理并保存
        for domain in ['music', 'movie', 'travel']:  # KdConv 有三个领域
            domain_file = kdconv_dir / f"kdconv_{domain}.json"
            data = []

            for split in dataset:
                for item in tqdm(dataset[split], desc=f"处理 {domain} {split}"):
                    data.append(item)

            with open(domain_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[SUCCESS] KdConv 数据集已保存到: {kdconv_dir}")

        return True

    except Exception as e:
        print(f"[ERROR] 下载失败: {e}")

    print("\n[INFO] 请手动从以下地址下载 KdConv 数据集：")
    print("       GitHub: https://github.com/thu-coai/KdConv")
    print("       下载后解压到:", kdconv_dir)

    return False


def download_personachat_chinese():
    """
    下载 PersonaChat 中文翻译版

    PersonaChat 是经典的人格对话数据集
    中文版可用于 Persona 建模测试
    """
    print("\n" + "="*60)
    print("下载 PersonaChat 中文版")
    print("="*60)

    pc_dir = DATASET_DIR / "PersonaChat"
    pc_dir.mkdir(exist_ok=True)

    try:
        from datasets import load_dataset
        print("[INFO] 使用 Hugging Face datasets 库下载...")

        # PersonaChat 英文版
        dataset = load_dataset("bavard/personachat_truecased")

        output_file = pc_dir / "personachat_data.json"
        data = []

        for split in dataset:
            for item in tqdm(dataset[split], desc=f"处理 {split}"):
                data.append(item)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[SUCCESS] PersonaChat 数据集已保存到: {output_file}")
        print("[INFO] 注意：这是英文版，建议使用翻译工具转换为中文")

        return True

    except Exception as e:
        print(f"[ERROR] 下载失败: {e}")

    return False


def download_from_github():
    """
    从 GitHub 直接下载公开数据集

    这些数据集可以直接通过 URL 下载
    """
    print("\n" + "="*60)
    print("从 GitHub 下载公开数据集")
    print("="*60)

    data_dir = DATASET_DIR / "github_datasets"
    data_dir.mkdir(exist_ok=True)

    # 可直接下载的数据集 URL
    datasets_urls = {
        "chinese_chatbot_corpus": {
            "url": "https://raw.githubusercontent.com/codemayq/chinese_chatbot_corpus/master/clean_chat_corpus/ptt_corpus.txt",
            "desc": "PTT 中文对话语料"
        },
        "douban_conversations": {
            "url": "https://raw.githubusercontent.com/MarkWuNLP/MultiTurnResponseSelection/master/data/ubuntu.txt",
            "desc": "Ubuntu 对话语料（示例）"
        }
    }

    success = 0
    for name, info in datasets_urls.items():
        print(f"\n下载: {info['desc']}")
        save_path = data_dir / f"{name}.txt"

        if download_file(info['url'], save_path):
            print(f"  ✅ 保存到: {save_path}")
            success += 1
        else:
            print(f"  ❌ 下载失败")

    return success > 0


def create_sample_dataset():
    """
    创建示例数据集（用于快速测试）

    如果下载失败，可以先用这个小规模数据集
    """
    print("\n" + "="*60)
    print("创建示例数据集")
    print("="*60)

    sample_dir = DATASET_DIR / "sample"
    sample_dir.mkdir(exist_ok=True)

    # 示例对话数据
    sample_data = [
        {
            "id": 1,
            "user_input": "今天好累啊",
            "responses": [
                {"persona": "casual", "text": "哎呀，辛苦啦～早点休息吧"},
                {"persona": "formal", "text": "您辛苦了，建议早点休息"},
                {"persona": "humorous", "text": "哈哈，今天又是搬砖的一天吗？"}
            ]
        },
        {
            "id": 2,
            "user_input": "周末有什么安排",
            "responses": [
                {"persona": "casual", "text": "没啥安排，可能在家躺平哈哈"},
                {"persona": "formal", "text": "周末我计划在家休息"},
                {"persona": "humorous", "text": "安排就是睡到自然醒！"}
            ]
        },
        {
            "id": 3,
            "user_input": "你觉得这个怎么样",
            "responses": [
                {"persona": "casual", "text": "还行吧，感觉可以～"},
                {"persona": "formal", "text": "我认为这个还不错"},
                {"persona": "humorous", "text": "嗯...让我想想，这个问题有点深奥哈哈"}
            ]
        }
    ]

    output_file = sample_dir / "sample_dialogues.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(sample_data, f, ensure_ascii=False, indent=2)

    print(f"[SUCCESS] 示例数据集已创建: {output_file}")

    return True


def check_dependencies():
    """检查依赖"""
    print("\n检查依赖...")

    required = ['requests', 'tqdm']
    optional = ['datasets']

    for pkg in required:
        try:
            __import__(pkg)
            print(f"  ✅ {pkg}")
        except ImportError:
            print(f"  ❌ {pkg} (请运行: pip install {pkg})")

    for pkg in optional:
        try:
            __import__(pkg)
            print(f"  ✅ {pkg}")
        except ImportError:
            print(f"  ⚠️ {pkg} (可选，用于自动下载 Hugging Face 数据集)")


def main():
    parser = argparse.ArgumentParser(description="下载中文对话数据集")
    parser.add_argument(
        '--dataset',
        type=str,
        default='all',
        choices=['lccc', 'cped', 'kdconv', 'personachat', 'github', 'sample', 'all'],
        help='要下载的数据集'
    )
    parser.add_argument(
        '--check',
        action='store_true',
        help='仅检查依赖'
    )

    args = parser.parse_args()

    print("="*60)
    print("中文对话数据集下载工具")
    print("="*60)
    print(f"数据集保存目录: {DATASET_DIR}")

    if args.check:
        check_dependencies()
        return

    # 检查依赖
    check_dependencies()

    # 下载数据集
    success_count = 0

    if args.dataset in ['lccc', 'all']:
        if download_lccc():
            success_count += 1

    if args.dataset in ['cped', 'all']:
        if download_cped():
            success_count += 1

    if args.dataset in ['kdconv', 'all']:
        if download_kdconv():
            success_count += 1

    if args.dataset in ['personachat', 'all']:
        if download_personachat_chinese():
            success_count += 1

    if args.dataset in ['github', 'all']:
        if download_from_github():
            success_count += 1

    if args.dataset in ['sample', 'all']:
        if create_sample_dataset():
            success_count += 1

    # 总结
    print("\n" + "="*60)
    print("下载完成")
    print("="*60)
    print(f"成功下载: {success_count} 个数据集")
    print(f"数据目录: {DATASET_DIR}")

    # 如果大部分下载失败，提供手动下载指南
    print("\n📚 手动下载指南:")
    print("-" * 40)
    print("1. LCCC:")
    print("   https://github.com/thu-coai/LCCC")
    print("2. CPED:")
    print("   https://github.com/scutcyr/CPED")
    print("3. KdConv:")
    print("   https://github.com/thu-coai/KdConv")
    print("4. PersonaChat:")
    print("   https://huggingface.co/datasets/bavard/personachat_truecased")


if __name__ == "__main__":
    main()