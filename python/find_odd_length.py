"""从 translations.json 中找出所有 length 为奇数的项。"""
import json
from pathlib import Path

def main():
    path = Path(__file__).resolve().parent.parent / "translate" / "translations.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    odd_items = [item for item in data if item.get("length", 0) % 2 != 0]
    print(f"共 {len(odd_items)} 项 length 为奇数:\n")
    for item in odd_items:
        print(f"  offset: {item['offset']}, length: {item['length']}")
        print(f"    original: {item['original']!r}")
        print(f"    translation: {item['translation']!r}")
        print()

if __name__ == "__main__":
    main()
