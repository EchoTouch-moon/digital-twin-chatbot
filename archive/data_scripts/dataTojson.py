import json
import datetime

# ================= 配置区域 =================
INPUT_FILE = 'wxdata_process\messages.json'  # 你的源文件名
OUTPUT_FILE = 'finetune_data.jsonl' # 输出文件名
SYSTEM_PROMPT = "你是一个数字孪生体，你需要模仿[高雪洁]的语气、性格和用词习惯与[墨黎笙]进行对话。"
TIME_THRESHOLD_MINUTES = 30 # 超过多少分钟视为新的一段对话
MIN_TURN_COUNT = 2 # 每一段对话至少包含几轮才保存（防止只有一句"在吗"）
# ===========================================

def process_wechat_data():
    print(f"正在读取 {INPUT_FILE} ...")
    
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            # 兼容处理：有的导出直接是列表，有的是字典包含列表
            if isinstance(raw_data, dict) and "messages" in raw_data:
                messages = raw_data["messages"]
            elif isinstance(raw_data, list):
                messages = raw_data
            else:
                raise ValueError("无法识别的JSON结构")
    except Exception as e:
        print(f"读取文件失败: {e}")
        return

    # 1. 按时间正序排序 (从小到大)
    print("正在排序数据...")
    messages.sort(key=lambda x: x['createTime'])

    final_conversations = []
    current_messages = []
    
    last_time = 0
    last_role = None
    buffer_content = [] # 用于合并连续发言

    # 统计数据
    total_msgs = len(messages)
    valid_text_msgs = 0
    skipped_stickers = 0

    print(f"开始处理 {total_msgs} 条原始消息...")

    for msg in messages:
        # --- 过滤逻辑 ---
        
        # 只保留文本消息 (Type 1 通常是文本，引用你提供的片段 type 47 是表情)
        # 如果你的文本也是 type 0 或其他，请根据实际情况修改这里
        # 注意：有时候 type 1 内容如果是 url 也需要过滤
        msg_type = msg.get('type')
        content = msg.get('content', '').strip()

        # 如果是表情包(47)或者内容为空，或者是其他非文本类型，跳过
        if msg_type == 47 or not content or content == "[表情]":
            skipped_stickers += 1
            continue
        
        # 简单过滤系统消息 (比如包含 XML 标签的消息通常是引用或转账)
        if content.startswith('<?xml') or '<msg>' in content:
            continue

        valid_text_msgs += 1

        # --- 角色判断 ---
        # isSent = True (你/User), isSent = False (她/Assistant)
        role = "user" if msg.get('isSent') else "assistant"
        timestamp = msg.get('createTime', 0)

        # --- 会话分割逻辑 (Sessionizing) ---
        # 如果距离上一条消息超过阈值，视为新对话，先保存上一轮
        if last_time > 0 and (timestamp - last_time) > (TIME_THRESHOLD_MINUTES * 60):
            if current_messages:
                # 只有当当前会话有内容时才保存
                add_conversation(final_conversations, current_messages)
                current_messages = []
                last_role = None # 重置上一条说话人
                buffer_content = []

        # --- 连续发言合并逻辑 ---
        if role == last_role:
            # 同一个人连续说话，加入 buffer
            buffer_content.append(content)
        else:
            # 换人说话了
            # 1. 先把上一个人的 buffer 存入 current_messages
            if buffer_content and last_role:
                joined_content = "，".join(buffer_content) # 用逗号或空格连接
                current_messages.append({"role": last_role, "content": joined_content})
            
            # 2. 重置 buffer 为当前这条消息
            buffer_content = [content]
            last_role = role

        last_time = timestamp

    # 循环结束后，处理最后遗留的数据
    if buffer_content and last_role:
        joined_content = "，".join(buffer_content)
        current_messages.append({"role": last_role, "content": joined_content})
    
    if current_messages:
        add_conversation(final_conversations, current_messages)

    # --- 保存到文件 ---
    print(f"\n处理完成！")
    print(f"原始消息: {total_msgs} | 纯文本: {valid_text_msgs} | 过滤表情: {skipped_stickers}")
    print(f"生成的对话组数: {len(final_conversations)}")
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for conv in final_conversations:
            f.write(json.dumps(conv, ensure_ascii=False) + '\n')
            
    print(f"文件已保存至: {OUTPUT_FILE}")

def add_conversation(final_list, raw_msgs):
    """
    构建符合微调格式的 entry
    格式: {"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]}
    """
    # 过滤掉只有 User 没有 Assistant 回复的对话，或者反之
    # 训练数据的基本逻辑通常是: User -> Assistant
    
    if len(raw_msgs) < 2:
        return

    # 确保对话以 User 开始 (可选，取决于模型，但通常建议)
    # 如果第一条是 Assistant，可以去掉，或者作为 Context (这里简化处理，直接去掉)
    while raw_msgs and raw_msgs[0]['role'] == 'assistant':
        raw_msgs.pop(0)
        
    if not raw_msgs: return

    # 构建最终结构
    entry = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT}
        ] + raw_msgs
    }
    
    final_list.append(entry)

if __name__ == "__main__":
    process_wechat_data()