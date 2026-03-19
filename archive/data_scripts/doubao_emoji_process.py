import os
import base64
import json
import time
from tqdm import tqdm
from openai import OpenAI
import logging

# -------------------------- 配置参数 --------------------------
# 请根据实际情况修改以下配置
DOUBAO_API_KEY = os.getenv("ARK_API_KEY")  # 从环境变量读取豆包API Key
DOUBAO_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"  # 豆包兼容OpenAI的基础地址
MODEL_NAME = "doubao-seed-1-8-251228"  # 豆包1.8多模态模型（可按需替换为8k版本）
EMOJI_DIR = "./emojis"  # 表情包本地存储目录
OUTPUT_JSONL_PATH = "./emoji_classification.jsonl"  # 输出JSONL文件路径
ERROR_LOG_PATH = "./emoji_process_errors.log"  # 错误日志路径
SUPPORTED_FORMATS = (".jpg", ".jpeg", ".png", ".gif", ".webp")  # 支持的图片格式
REQUEST_INTERVAL = 1.5  # API调用间隔（避免限流，可根据豆包配额调整）

# -------------------------- 初始化配置 --------------------------
# 配置日志记录
logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(ERROR_LOG_PATH), logging.StreamHandler()]
)

# 初始化OpenAI兼容客户端
client = OpenAI(
    api_key=DOUBAO_API_KEY,
    base_url=DOUBAO_BASE_URL
)

# -------------------------- 工具函数 --------------------------
def image_to_base64(image_path: str) -> str:
    """将本地图片转换为base64字符串"""
    with open(image_path, "rb") as image_file:
        encoded = base64.b64encode(image_file.read()).decode("utf-8")
    return encoded

def analyze_emoji(image_path: str) -> dict:
    """调用豆包1.8多模态模型分析表情包，返回两级分类+描述"""
    # 构造严格的Prompt，强制模型输出指定格式的JSON
    prompt = """请你分析这张表情包的内容，严格按照以下要求输出JSON格式数据，不要添加任何额外解释：
1. 一级分类(top_category)：必须从以下选项中选择：开心、生气、伤心、惊讶、无奈、嘲讽、卖萌、感动、其他；若无法匹配现有分类则选"其他"
2. 二级分类(sub_category)：对一级分类的细分，比如一级为"开心"时，二级可以是"大笑、偷笑、得意、惊喜"等具体场景
3. description：详细描述表情包的画面内容、情绪含义及适用场景，语言要准确

输出示例：
{"top_category":"开心","sub_category":"大笑","description":"一只卡通熊猫张嘴大笑，眼睛眯成月牙，表情夸张，适合表达极度开心、兴奋的情绪，常用于分享好消息或调侃时"}"""

    try:
        # 图片转base64
        image_b64 = image_to_base64(image_path)
        
        # 调用豆包多模态API
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_b64}"}
                        }
                    ]
                }
            ],
            temperature=0.1,  # 降低随机性，保证分类一致性
            response_format={"type": "json_object"}  # 强制返回JSON格式
        )
        
        # 解析模型返回结果
        result = json.loads(response.choices[0].message.content)
        # 补充原文件名到结果中，方便关联
        result["file_name"] = os.path.basename(image_path)
        return result
    
    except Exception as e:
        error_msg = f"处理图片 {image_path} 失败: {str(e)}"
        logging.error(error_msg)
        return None

# -------------------------- 主处理流程 --------------------------
def process_all_emojis():
    """遍历所有表情包，批量处理并写入JSONL文件"""
    # 获取所有表情包文件
    emoji_files = [
        os.path.join(EMOJI_DIR, f) 
        for f in os.listdir(EMOJI_DIR)
        if f.lower().endswith(SUPPORTED_FORMATS)
    ]
    
    if not emoji_files:
        print(f"在目录 {EMOJI_DIR} 中未找到支持格式的表情包文件")
        return
    
    print(f"共发现 {len(emoji_files)} 个表情包，开始处理...")
    
    # 打开输出文件，逐行写入
    with open(OUTPUT_JSONL_PATH, "w", encoding="utf-8") as out_f:
        # 使用tqdm显示进度条
        for file_path in tqdm(emoji_files, desc="处理进度"):
            result = analyze_emoji(file_path)
            if result:
                # 将结果转为JSON字符串，写入文件（每行一个JSON对象）
                json.dump(result, out_f, ensure_ascii=False)
                out_f.write("\n")
            # 控制调用间隔，避免限流
            time.sleep(REQUEST_INTERVAL)
    
    print(f"处理完成！结果已保存至 {OUTPUT_JSONL_PATH}，错误日志在 {ERROR_LOG_PATH}")

if __name__ == "__main__":
    # 检查API Key是否配置
    if not DOUBAO_API_KEY:
        print("错误：请先设置环境变量DOUBAO_API_KEY（从豆包开放平台获取）")
    else:
        process_all_emojis()