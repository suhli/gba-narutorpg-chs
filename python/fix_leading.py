#!/usr/bin/env python3
"""
修复 JSON 中多余的前导字节（对应单字符）：
- hex 以 28/29/30/31/32 开头（(、)、0、1、2），且 original 以对应字符开头
- 同时校验 length % 2 != 0（长度为奇数）才处理
- 去掉 hex 前两字符、原文（及译文若匹配）首字符，offset +1，length -1

处理：
- translate/translations.json：要求 translation 也以同字符开头才修复
- debug/text_dump/*.json：不校验 translation，只按 hex + original 修复
"""

import json
import sys
from pathlib import Path

# 前导字节(hex 前两位) -> 对应的首字符
LEADING_HEX_TO_CHAR = {
    "20": " ",   # 空格
    "21": "!",   # !
    "22": "\"",   # "
    "23": "#",   # #
    "25": "%",   # %
    "26": "&",   # &
    "27": "'",   # '
    "28": "(",   # (
    "29": ")",   # )
    "2A": "*",   # *
    "2B": "+",   # +
    "2C": ",",   # ,
    "2D": "-",   # -
    "2E": ".",   # .
    "2F": "/",   # /
    "30": "0",   # 0
    "31": "1",   # 1
    "32": "2",   # 2
    "30": "0",   # 0
    "31": "1",   # 1
    "32": "2",   # 2
}


def fix_leading_in_data(data, require_translation_leading=True):
    """对一条条目的列表做前导字节修复，返回修复条数。"""
    count = 0
    for item in data:
        hex_str = item.get("hex", "")
        original = item.get("original", "")
        translation = item.get("translation", "")
        length = item.get("length", 0)

        if length % 2 == 0:
            continue

        for hex_prefix, char in LEADING_HEX_TO_CHAR.items():
            if not hex_str.startswith(hex_prefix) or not original.startswith(char):
                continue
            need_translation_ok = (
                translation.startswith(char) if require_translation_leading else True
            )
            if not need_translation_ok:
                continue

            # 去掉 hex 前两字符（一个字节）
            item["hex"] = hex_str[2:]
            # 去掉原文首字符
            item["original"] = original[1:]
            # 译文仅当以同字符开头时才去掉
            if translation.startswith(char):
                item["translation"] = translation[1:]
            # offset +1，length -1
            offset_val = int(item["offset"], 16)
            item["offset"] = f"0x{offset_val + 1:X}"
            item["length"] = length - 1
            count += 1
            break
    return count


def main():
    repo_root = Path(__file__).resolve().parent.parent
    python_dir = Path(__file__).resolve().parent

    # 1) translate/translations.json：校验 translation 以 "1" 开头
    json_path = repo_root / "translate" / "translations.json"
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        count = fix_leading_in_data(data, require_translation_leading=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[translations.json] 已修复 {count} 条记录。", file=sys.stderr)
    else:
        print(f"[translations.json] 未找到，跳过。", file=sys.stderr)

    # 2) debug/text_dump/*.json：不校验 translation 以 "1" 开头
    text_dump_dir = python_dir / "debug" / "text_dump"
    if not text_dump_dir.is_dir():
        print(f"[text_dump] 目录不存在，跳过。", file=sys.stderr)
        return

    total_dump = 0
    for p in sorted(text_dump_dir.glob("*.json")):
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        count = fix_leading_in_data(data, require_translation_leading=False)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        if count > 0:
            print(f"[{p.name}] 已修复 {count} 条记录。", file=sys.stderr)
        total_dump += count

    print(f"[text_dump] 共修复 {total_dump} 条记录。", file=sys.stderr)


if __name__ == "__main__":
    main()
