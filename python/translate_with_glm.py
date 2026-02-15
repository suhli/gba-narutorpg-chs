#!/usr/bin/env python3
"""
使用 GLM-4 / GLM-4.7（智谱 ChatGPT 兼容入口）翻译 python/debug/text_dump 下的 JSON 文本，
翻译结果保存到项目目录/translate/，不修改源文件。

依赖：
  pip install -r requirements.txt   # openai, python-dotenv

配置：
  从项目根目录或 python 目录下的 .env 读取，参考 .env.example。
  GLM_API_KEY 或 ZHIPU_API_KEY  智谱 API Key（必填）
  GLM_BASE_URL                  可选，默认 https://open.bigmodel.cn/api/paas/v4
  GLM_MODEL                     可选，默认 glm-4-plus

使用：
  cd python && python translate_with_glm.py              # 翻译所有 chunk，每批 100 条（结构化 JSON），跳过已有译文
  python translate_with_glm.py --batch-size 100 --dry-run
  python translate_with_glm.py --no-skip                  # 全部重翻（已 skiped 的条仍不重发）
  python translate_with_glm.py --model glm-4-plus --files text_chunk_001.json
"""

import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# 项目内 instruction 路径
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# 项目根目录（脚本在 python/ 下）
PROJECT_ROOT = SCRIPT_DIR.parent
# 从项目根或 python 目录加载 .env
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(SCRIPT_DIR / ".env")

TEXT_DUMP_DIR = SCRIPT_DIR / "debug" / "text_dump"
OUTPUT_DIR = PROJECT_ROOT / "translate"  # 翻译结果保存到此目录，不写回源文件
TRANSLATIONS_OUTPUT_PATH = OUTPUT_DIR / "translations.json"  # 唯一输出文件，每条翻译后追加保存
INSTRUCTION_PATH = SCRIPT_DIR / "translate.instruction.md"

# 默认使用智谱 OpenAI 兼容 API（GLM-4 系列），配置从 .env 读取
DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
DEFAULT_MODEL = "glm-4-plus"  # 可选 glm-4, glm-4-plus 等

# 逐条翻译，每轮请求只发一条；对话历史只保留最近 N 轮，避免上下文过长
MAX_HISTORY_TURNS = 10  # 保留最近 10 轮（每轮 = user + assistant）

# 结构化批量：每批 N 条，输入/输出均为 JSON 数组，便于长度对齐
BATCH_SIZE = 100


def get_client() -> OpenAI:
    raw = os.environ.get("GLM_API_KEY") or os.environ.get("ZHIPU_API_KEY")
    # 防止 .env 里同一行写注释导致 key 带上中文，HTTP 头 ascii 编码报错
    api_key = (raw or "").split("#")[0].strip()
    if not api_key:
        print("请在 .env 中设置 GLM_API_KEY 或 ZHIPU_API_KEY（智谱 API Key）", file=sys.stderr)
        sys.exit(1)
    base_url = os.environ.get("GLM_BASE_URL", DEFAULT_BASE_URL)
    return OpenAI(api_key=api_key, base_url=base_url)


def load_instruction() -> str:
    if not INSTRUCTION_PATH.exists():
        raise FileNotFoundError(f"未找到 {INSTRUCTION_PATH}")
    return INSTRUCTION_PATH.read_text(encoding="utf-8")


def list_chunk_files() -> list[Path]:
    if not TEXT_DUMP_DIR.exists():
        return []
    files = sorted(TEXT_DUMP_DIR.glob("text_chunk_*.json"))
    return files


def extract_json_array(text: str) -> list[dict]:
    """从模型回复中提取 JSON 数组（可能被包在 ```json ... ``` 中）。"""
    text = (text or "").strip()
    # 尝试匹配 ```json ... ``` 或 ``` ... ```
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        text = m.group(1).strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        return []
    except json.JSONDecodeError:
        pass
    # 尝试直接找 [ ... ] 块
    start = text.find("[")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "[":
                depth += 1
            elif text[i] == "]":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
    return []


def align_length(translated: str, original: str) -> str:
    """使译文与原文的 Unicode 字符数一致：不足补空格，过长截断/压缩（由调用方尽量先控制）。"""
    orig_len = len(original)
    trans = (translated or "").strip()
    if len(trans) == orig_len:
        return trans
    if len(trans) < orig_len:
        # 优先用与原文一致的空格：原文尾若是全角则补全角
        tail = original.strip()
        if tail and (original.endswith("　") or "　" in original[-10:]):
            space = "　"
        else:
            space = " "
        return trans + space * (orig_len - len(trans))
    return trans[:orig_len]


def to_instruction_input(entry: dict) -> list[dict]:
    """转换为 instruction 规定的输入格式：仅含 offset、text 的 JSON 数组（单条）。"""
    return [{"offset": entry["offset"], "text": entry["original"]}]


def _truncate_messages(messages: list[dict], max_turns: int = MAX_HISTORY_TURNS) -> list[dict]:
    """只保留 system + 最近 max_turns 轮对话（每轮 = user + assistant），避免上下文过长。"""
    if not messages or len(messages) <= 1 + max_turns * 2:
        return messages
    # messages[0] 为 system，其余为 user/assistant 交替
    keep = 1 + max_turns * 2  # system + 最近 max_turns 对
    return messages[:1] + messages[-keep + 1 :]

def translate_one(
    client: OpenAI,
    model: str,
    messages: list[dict],
    entry: dict,
) -> tuple[dict, list[dict]]:
    """发送单条条目翻译，返回 (单条结果, 更新后的 messages)。"""
    inputs = to_instruction_input(entry)
    user_content = "请将以下 JSON 数组中的日文翻译成中文（仅输出 JSON 数组，不要其他说明）：\n"
    user_content += json.dumps(inputs, ensure_ascii=False, indent=2)

    messages = _truncate_messages(messages)
    new_messages = messages + [{"role": "user", "content": user_content}]
    offset = entry["offset"]
    orig = entry["original"]
    out: dict = {"offset": offset, "text": orig, "skiped": False}

    resp = client.chat.completions.create(
        model=model,
        messages=new_messages,
        temperature=0.3,
    )
    choice = resp.choices[0] if resp.choices else None
    content = (choice.message.content or "").strip() if choice and getattr(choice, "message", None) else ""
    if not content:
        return out, new_messages
    out_list = extract_json_array(content)
    item = next((x for x in out_list if str(x.get("offset", "")) == str(offset)), None)
    if item is not None:
        trans = item.get("text", "")
        skiped = item.get("skiped", False)
        if skiped:
            out["text"] = orig
            out["skiped"] = True
        else:
            out["text"] = align_length(trans, orig)
            out["skiped"] = False
    return out, new_messages


def to_batch_input(entries_batch: list[dict]) -> list[dict]:
    """将一批条目转为 instruction 规定的输入格式：仅含 offset、text 的 JSON 数组。"""
    return [{"offset": e["offset"], "text": e.get("original", "")} for e in entries_batch]


def translate_batch(
    client: OpenAI,
    model: str,
    instruction: str,
    entries_batch: list[dict],
) -> list[dict]:
    """批量翻译：输入为 JSON 数组（多条），输出为 JSON 数组，顺序与 offset 严格对应。
    返回与 entries_batch 等长的列表，每项为 {"offset", "text", "skiped"}。
    """
    if not entries_batch:
        return []
    inputs = to_batch_input(entries_batch)
    user_content = "请将以下 JSON 数组中的日文翻译成中文（仅输出 JSON 数组，不要其他说明）：\n"
    user_content += json.dumps(inputs, ensure_ascii=False, indent=2)
    new_messages = [
        {"role": "system", "content": instruction},
        {"role": "user", "content": user_content},
    ]
    resp = client.chat.completions.create(
        model=model,
        messages=new_messages,
        temperature=0.3,
    )
    choice = resp.choices[0] if resp.choices else None
    content = (choice.message.content or "").strip() if choice and getattr(choice, "message", None) else ""
    out_list = extract_json_array(content) if content else []
    by_offset = {str(x.get("offset", "")): x for x in out_list if isinstance(x, dict)}
    results = []
    for e in entries_batch:
        offset = e.get("offset")
        orig = e.get("original", "")
        item = by_offset.get(str(offset))
        if item is not None:
            trans = item.get("text", "")
            skiped = item.get("skiped", False)
            if skiped:
                results.append({"offset": offset, "text": orig, "skiped": True})
            else:
                results.append({"offset": offset, "text": align_length(trans, orig), "skiped": False})
        else:
            results.append({"offset": offset, "text": orig, "skiped": True})
    return results


def load_translations_file() -> list[dict]:
    """从唯一输出文件读取已翻译数组，不存在或异常时返回空列表。"""
    if not TRANSLATIONS_OUTPUT_PATH.exists():
        return []
    try:
        data = json.loads(TRANSLATIONS_OUTPUT_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError):
        return []


def save_translations_file(entries: list[dict], *, skip_filled: bool = True) -> None:
    """将当前条目的 translation/skiped/hex 等合并到唯一输出文件并写回（JSON 数组）。
    当 skip_filled 为 True（未传 --no-skip）时，已存在的行（含 skiped）也会用当前条目的 original/hex 更新。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    existing = load_translations_file()
    by_offset = {str(e.get("offset", "")): e for e in existing if isinstance(e, dict)}
    for e in entries:
        if not isinstance(e, dict):
            continue
        offset = e.get("offset")
        if offset is None:
            continue
        key = str(offset)
        row = by_offset.get(key)
        if row is None:
            row = {
                "offset": offset,
                "hex": e.get("hex", ""),
                "length": e.get("length"),
                "original": e.get("original", ""),
                "translation": e.get("translation", ""),
                "skiped": e.get("skiped", False),
            }
            by_offset[key] = row
        else:
            row["translation"] = e.get("translation", "")
            row["skiped"] = e.get("skiped", False)
            if skip_filled:
                row["original"] = e.get("original", "")
                row["hex"] = e.get("hex", "")
                if "length" in e:
                    row["length"] = e.get("length")
            else:
                if e.get("hex") is not None:
                    row["hex"] = e.get("hex", "")
                if "length" in e:
                    row["length"] = e.get("length")
    out_list = list(by_offset.values())
    TRANSLATIONS_OUTPUT_PATH.write_text(
        json.dumps(out_list, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_all_entries(chunk_files: list[Path]) -> list[dict]:
    """合并所有 chunk 文件为一条列表，保留 offset/hex/length/original 等字段。"""
    all_entries: list[dict] = []
    for path in chunk_files:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            print(f"  [{path.name}] 读取失败，跳过", file=sys.stderr)
            continue
        if not isinstance(raw, list):
            continue
        for e in raw:
            if isinstance(e, dict) and "original" in e:
                all_entries.append(dict(e))
    return all_entries


def process_all(
    client: OpenAI,
    model: str,
    instruction: str,
    all_entries: list[dict],
    *,
    batch_size: int = BATCH_SIZE,
    skip_filled: bool = True,
    dry_run: bool = False,
) -> None:
    """对所有条目按批翻译（结构化 JSON），结果写入 translate/translations.json。"""
    # 始终加载已有结果，合并 translation/skiped；--no-skip 时已 skiped 的条也不重发
    out_data = load_translations_file()
    by_offset = {
        e.get("offset"): {"translation": e.get("translation", ""), "skiped": e.get("skiped", False)}
        for e in out_data if isinstance(e, dict)
    }
    for e in all_entries:
        o = by_offset.get(e.get("offset"))
        if o and (o["translation"] or o["skiped"]):
            e["translation"] = o["translation"]
            e["skiped"] = o["skiped"]

    to_translate = [
        e
        for e in all_entries
        if "original" in e
        and not e.get("skiped")
        and (not skip_filled or not (e.get("translation") or "").strip())
    ]

    if not to_translate:
        print(f"  无需翻译（共 {len(all_entries)} 条）")
        return

    print(f"  待翻译 {len(to_translate)} / {len(all_entries)} 条（结构化 JSON，每批 {batch_size} 条）")
    if dry_run:
        return

    offset_to_entry = {e["offset"]: e for e in all_entries}
    num_batches = (len(to_translate) + batch_size - 1) // batch_size
    for b in range(num_batches):
        start = b * batch_size
        chunk = to_translate[start : start + batch_size]
        try:
            results = translate_batch(client, model, instruction, chunk)
        except Exception as exc:
            print(f"  第 {b + 1}/{num_batches} 批失败: {exc}", file=sys.stderr)
            raise
        for r in results:
            ent = offset_to_entry.get(r["offset"])
            if ent is not None:
                ent["translation"] = r["text"]
                ent["skiped"] = r.get("skiped", False)
        save_translations_file(all_entries, skip_filled=skip_filled)
        print(f"    已翻译第 {b + 1}/{num_batches} 批（本批 {len(chunk)} 条）")
    print(f"  已写入 {TRANSLATIONS_OUTPUT_PATH}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="使用 GLM-4 翻译 text_dump 下的 JSON")
    parser.add_argument(
        "--model",
        default=os.environ.get("GLM_MODEL", DEFAULT_MODEL),
        help="模型名（也可在 .env 中设置 GLM_MODEL）",
    )
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help=f"每批条数（默认 {BATCH_SIZE}）")
    parser.add_argument("--no-skip", action="store_true", help="不跳过已有 translation 的条目，全部重翻")
    parser.add_argument("--dry-run", action="store_true", help="只列出待翻译文件与条数，不请求 API")
    parser.add_argument("--files", nargs="*", help="仅处理这些 chunk 文件（例如 text_chunk_001.json）")
    args = parser.parse_args()

    instruction = load_instruction()
    client = get_client()
    files = list_chunk_files()
    if args.files:
        by_name = {p.name: p for p in files}
        files = [by_name[n] for n in args.files if n in by_name]
    if not files:
        print(f"在 {TEXT_DUMP_DIR} 下未找到 text_chunk_*.json")
        return

    all_entries = load_all_entries(files)
    if not all_entries:
        print("没有可翻译的条目")
        return

    print(f"输出文件: {TRANSLATIONS_OUTPUT_PATH}")
    print(f"已合并 chunk 数: {len(files)}，总条数: {len(all_entries)}")
    process_all(
        client,
        args.model,
        instruction,
        all_entries,
        batch_size=args.batch_size,
        skip_filled=not args.no_skip,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
