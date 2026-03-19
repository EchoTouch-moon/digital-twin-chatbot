import os
import json
import time
from http import HTTPStatus
import dashscope

# ================= 配置区域 =================
# 1. 在这里填入你的 API Key
api_key = os.getenv('ARK_API_KEY')

# 2. 文件夹路径
MEDIA_DIR = 'downloaded_media/emojis'  # 表情包所在的文件夹
OUTPUT_MAPPING_FILE = 'emoji_mapping.json' # 结果保存的文件名

# 3. 指定模型
MODEL_NAME = 'qwen3-vl-flash' 
 # enable_thinking 参数开启思考过程
enable_thinking=True,
    # thinking_budget 参数设置最大推理过程 Token 数
thinking_budget=81920,
# ===========================================

def generate_caption_via_api(file_path):
    """调用 API 识别单张图片"""
    # Windows 路径需要转换为 file:// 协议格式，且要是绝对路径
    abs_path = os.path.abspath(file_path)
    local_file_url = f"file://{abs_path}"

    messages = [
        {
            "role": "user",
            "content": [
                {"image": local_file_url},
                {
                    "text": (
                        "你是一个构建数字孪生聊天机器人的数据标注专家。请对这张表情包进行多维度的描述。"
                        "\n\n请按照以下步骤思考："
                        "1. **视觉识别**：看清图片的主体（是熊猫头、猫、狗、还是真人？）、动作和神态。"
                        "2. **文字提取**：如果图片上有文字，必须完整读出来。"
                        "3. **含义推断**：结合画面和文字，推断这在聊天中想表达的潜台词（是嘲讽、撒娇、无奈还是愤怒？）。"
                        "\n\n最后，请严格按照以下格式输出（不要输出思考过程，只输出最终结果）："
                        "\n格式要求：[表情：<简练的画面描述>，配文“<图片文字>”，表示<深层含义/情绪>]"
                        "\n\n示例："
                        "\n- [表情：流泪的熊猫头，配文“我太难了”，表示生活压力大和委屈]"
                        "\n- [表情：一只柴犬被捏住脸，表示无奈和被迫营业]"
                        "\n- [表情：张学友那张经典的指人图，配文“食屎啦你”，表示强烈的鄙视和愤怒]"
                        "\n- [表情：一个旋转的问号，表示极度困惑]"
                    )
                }
            ]
        }
    ]

    try:
        response = dashscope.MultiModalConversation.call(
            model=MODEL_NAME,
            messages=messages
        )
        
        if response.status_code == HTTPStatus.OK:
            # --- 修复部分开始 ---
            content = response.output.choices[0].message.content
            
            # 如果返回的是列表（List），提取里面的 text 字段
            if isinstance(content, list):
                # 遍历列表，把所有 'text' 内容拼起来
                text_content = ""
                for item in content:
                    if isinstance(item, dict) and 'text' in item:
                        text_content += item['text']
                return text_content
            
            # 如果返回的是字符串，直接返回
            return content
            # --- 修复部分结束 ---
            
        else:
            print(f"\nAPI 报错: {response.code} - {response.message}")
            return None
    except Exception as e:
        print(f"\n请求异常: {e}")
        return None

def main():
    if not dashscope.api_key or "你的API_KEY" in dashscope.api_key:
        print("错误：请先在脚本中填入你的 DashScope API Key！")
        return

    # 1. 读取已有进度 (断点续传)
    if os.path.exists(OUTPUT_MAPPING_FILE):
        print("发现已有进度文件，正在加载...")
        with open(OUTPUT_MAPPING_FILE, 'r', encoding='utf-8') as f:
            mapping = json.load(f)
    else:
        mapping = {}

    # 2. 扫描文件
    if not os.path.exists(MEDIA_DIR):
        print(f"错误：找不到文件夹 {MEDIA_DIR}")
        return

    # 支持常见的表情包格式
    files = [f for f in os.listdir(MEDIA_DIR) if f.lower().endswith(('.gif', '.jpg', '.png', '.jpeg', '.webp'))]
    total_files = len(files)
    print(f"文件夹中共有 {total_files} 个文件，已处理 {len(mapping)} 个。")

    # 3. 开始循环处理
    for i, filename in enumerate(files):
        # 如果已经识别过，直接跳过
        if filename in mapping:
            continue
            
        file_path = os.path.join(MEDIA_DIR, filename)
        print(f"[{i+1}/{total_files}] 正在处理: {filename} ...", end="", flush=True)
        
        # 调用 API
        caption = generate_caption_via_api(file_path)
        
        if caption:
            # 简单的格式清洗
            clean_text = caption.replace('\n', ' ').strip()
            if not clean_text.startswith("["):
                clean_text = f"[表情：{clean_text}]"
            
            mapping[filename] = clean_text
            print(f" 成功 -> {clean_text[:30]}...")
            
            # 每成功 5 张保存一次，防止数据丢失
            if len(mapping) % 5 == 0:
                with open(OUTPUT_MAPPING_FILE, 'w', encoding='utf-8') as f:
                    json.dump(mapping, f, ensure_ascii=False, indent=2)
            
            # 避免触发限流 (免费版 QPS 较低，建议暂停 1 秒)
            time.sleep(1.0) 
        else:
            print(" 跳过 (失败)")

    # 4. 最后保存一次
    with open(OUTPUT_MAPPING_FILE, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    
    print("\n全部完成！结果已保存到 emoji_mapping.json")

if __name__ == "__main__":
    main()