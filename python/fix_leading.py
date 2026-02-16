#!/usr/bin/env python3
"""
修复 translations.json 中多余的前导 "1"：
- hex 以 31 开头、original 和 translation 以 "1" 开头的条目
- 去掉 hex 开头的 31、原文和译文的开头的 "1"
- offset +1，length -1
"""

import json
import sys
from pathlib import Path


def main():
    repo_root = Path(__file__).resolve().parent.parent
    json_path = repo_root / "translate" / "translations.json"

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    count = 0
    for item in data:
        hex_str = item.get("hex", "")
        original = item.get("original", "")
        translation = item.get("translation", "")

        if (
            hex_str.startswith("31")
            and original.startswith("1")
            and translation.startswith("1")
        ):
            # 去掉 hex 开头的 31（一个字节 = 两个十六进制字符）
            item["hex"] = hex_str[2:]
            # 去掉原文和译文开头的 "1"
            item["original"] = original[1:]
            item["translation"] = translation[1:]
            # offset +1
            offset_val = int(item["offset"], 16)
            item["offset"] = f"0x{offset_val + 1:X}"
            # length -1
            item["length"] = item["length"] - 1
            count += 1

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"已修复 {count} 条记录。", file=sys.stderr)


if __name__ == "__main__":
    main()
