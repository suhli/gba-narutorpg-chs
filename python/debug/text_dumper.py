import json
import os
import math
import re
# --- 扩展配置 ---
ROM_PATH = "hexproj/original.gba"
OUTPUT_DIR = "python/debug/text_dump"
CHUNK_SIZE = 500
MIN_TEXT_LEN = 4
CLUSTER_THRESHOLD = 0x200
START_OFFSET = 0x6DA84
MEANINGFUL_CHAR_PATTERN = re.compile(r'[ぁ-んァ-ヶ\u4E00-\u9FAF\uFF66-\uFF9F]')
# 假设你的码表是一个简单的文本文件或字典
# 如果你的码表是二进制的，需要根据你的 [u16key][u16val] 结构解析
def load_binary_charset(bin_path):
    """
    解析二进制码表 [u16 key][u16 value]
    并返回一个包含所有合法字符的 set
    """
    if not os.path.exists(bin_path):
        print(f"警告: 找不到码表文件 {bin_path}，将跳过码表过滤。")
        return None
    
    valid_chars = set()
    with open(bin_path, 'rb') as f:
        data = f.read()
    
    # 每个条目 4 字节 (u16 + u16)
    entry_count = len(data) // 4
    print(f"正在加载码表，共 {entry_count} 个条目...")

    for i in range(entry_count):
        # 读取前两个字节作为 key (小端序)
        low_byte = data[i*4]
        high_byte = data[i*4 + 1]
        sjis_bytes = bytes([high_byte, low_byte])
        # 尝试将 key 转换为字符
        # 这种方式兼容你的查码表函数逻辑
        try:
            # GBA 是小端序，但 Shift-JIS 双字节在码表中通常按大端序存储
            # 如果你的 key 存储是小端序，这里用 'little'，否则用 'big'
            # 大多数 GBA 码表 key 会保持 SJIS 原始顺序 (Big-endian)
            char = sjis_bytes.decode('shift-jis')
            valid_chars.add(char)
        except UnicodeDecodeError:
            # 如果无法解码，说明可能不是标准的 SJIS 字符，或者存储序有误
            # 也可以尝试直接存 hex 字符串进行比对
            pass

    print(f"码表加载完成，有效字符去重后共: {len(valid_chars)} 个")
    return valid_chars

def is_sjis_first_byte(b):
    return (0x81 <= b <= 0x9F) or (0xE0 <= b <= 0xEF)

def dump_all_sjis(rom_path, charset=None):
    if not os.path.exists(rom_path):
        return []
    
    with open(rom_path, 'rb') as f:
        rom_data = f.read()

    raw_results = []
    # 直接从你的上边界开始，无视前面的代码区
    offset = START_OFFSET 
    rom_len = len(rom_data)

    print(f"从 {hex(START_OFFSET)} 开始精准扫描...")

    while offset < rom_len:
        chunk_start = offset
        temp_hex = []
        temp_text = ""
        
        while offset < rom_len:
            b1 = int(rom_data[offset])

            # 1. 双字节 SJIS
            if (0x81 <= b1 <= 0x9F) or (0xE0 <= b1 <= 0xEF):
                if offset + 1 < rom_len:
                    b2 = int(rom_data[offset + 1])
                    try:
                        char = rom_data[offset:offset+2].decode('shift-jis')
                        if charset is not None and char not in charset:
                            break
                        temp_text += char
                        temp_hex.extend([b1, b2])
                        offset += 2
                        continue
                    except UnicodeDecodeError: break
                else: break

            # 2. 半角区域 (ASCII & 半角片假名)
            elif (0x20 <= b1 <= 0x7E) or (0xA1 <= b1 <= 0xDF):
                try:
                    char = rom_data[offset:offset+1].decode('shift-jis')
                    if charset is not None and b1 > 0x7F:
                        if char not in charset: break
                    temp_text += char
                    temp_hex.append(b1)
                    offset += 1
                    continue
                except: break
            
            # 3. 遇到非文字（CMD、0x00等）立即断开
            else:
                break

        # --- 片段准入过滤 ---
        if len(temp_hex) >= MIN_TEXT_LEN:
            # 统计这个片段里到底有多少个“真文字”
            meaningful_chars = MEANINGFUL_CHAR_PATTERN.findall(temp_text)
            
            # 过滤掉像 rも$ 这种只有一个假名带一堆符号的残余
            # 真正的台词至少会有两个以上的汉字或假名
            if len(meaningful_chars) >= 2:
                raw_results.append({
                    "offset": chunk_start,
                    "length": len(temp_hex),
                    "hex": bytes(temp_hex).hex().upper(),
                    "original": temp_text,
                    "translation": ""
                })
        
        offset += 1 # 继续步进
        
    return raw_results
def filter_noise(data_list, cluster_threshold=0x200):
    if not data_list: return []
    
    data_list.sort(key=lambda x: x['offset'])
    print(f"开始深度脱水过滤...")
    
    final_output = []
    
    # 1. 匹配控制符标签
    cmd_pattern = re.compile(r'\[CMD_[0-9A-F]{2}\]')

    for i in range(len(data_list)):
        current = data_list[i]
        text_content = current['original']
        
        # 先去掉 [CMD_XX] 标签
        pure_text = cmd_pattern.sub('', text_content).strip()
        
        # --- 核心逻辑 ---
        
        # 如果长度太短（比如就一个字符），通常是杂质
        if len(pure_text) < 1:
            continue
            
        # 判定：是否含有假名或汉字
        # 像你说的 @B。、h,!AＱ、rも$ 
        # rも$ 会被保留（因为有 'も'），但 @B。这种纯符号会被过滤
        if not MEANINGFUL_CHAR_PATTERN.search(pure_text):
            continue
            
        # 如果你觉得 rも$ 这种带一个假名的还是干扰，可以加个比例：
        # total_len = len(pure_text)
        # meaningful_len = len(meaningful_pattern.findall(pure_text))
        # if meaningful_len / total_len < 0.3: continue

        # --- 空间连续性校验 ---
        curr_off = current['offset']
        curr_len = current['length']
        prev_dist = curr_off - (data_list[i-1]['offset'] + data_list[i-1]['length']) if i > 0 else 999999
        next_dist = data_list[i+1]['offset'] - (curr_off + curr_len) if i < len(data_list)-1 else 999999
        
        if min(prev_dist, next_dist) <= cluster_threshold or curr_len >= 20:
            item = current.copy()
            item['offset'] = hex(item['offset']).upper().replace("0X", "0x")
            final_output.append(item)
            
    print(f"脱水完成，剩余片段: {len(final_output)}")
    return final_output


def save_chunks(data_list):
    """分卷保存"""
    if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
    total = len(data_list)
    num_chunks = math.ceil(total / CHUNK_SIZE)
    
    for i in range(num_chunks):
        chunk = data_list[i*CHUNK_SIZE : (i+1)*CHUNK_SIZE]
        name = os.path.join(OUTPUT_DIR, f"text_chunk_{i+1:03d}.json")
        with open(name, "w", encoding="utf-8") as f:
            json.dump(chunk, f, ensure_ascii=False, indent=2)
    print(f"已保存 {num_chunks} 个文件到 {OUTPUT_DIR}")

if __name__ == "__main__":
    # 1. 加载你的码表文件
    # 建议你先导出一份当前游戏的字表（包含日文假名和常用汉字）
    my_charset = load_binary_charset("python/debug/charsets.binary") 
    
    # 2. 执行带字符校验的扫描
    raw_data = dump_all_sjis(ROM_PATH, charset=my_charset)
    
    # 3. 空间连续性过滤
    final_data = filter_noise(raw_data)
    
    # 4. 分卷保存
    save_chunks(final_data)