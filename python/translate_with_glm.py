#!/usr/bin/env python3
"""
使用 GLM-4 / GLM-4.7（智谱 ChatGPT 兼容入口）翻译 python/debug/text_dump 下的 JSON 文本，
并配合 Memori 术语记忆库保证一致性。翻译结果保存到项目目录/translate/，不修改源文件。

依赖：
  pip install -r requirements.txt   # openai, python-dotenv

配置：
  从项目根目录或 python 目录下的 .env 读取，参考 .env.example。
  GLM_API_KEY 或 ZHIPU_API_KEY  智谱 API Key（必填）
  GLM_BASE_URL                  可选，默认 https://open.bigmodel.cn/api/paas/v4
  GLM_MODEL                     可选，默认 glm-4-plus

使用：
  cd python && python translate_with_glm.py              # 翻译所有 chunk，跳过已有译文
  python translate_with_glm.py --dry-run                  # 仅查看待翻译条数
  python translate_with_glm.py --no-skip                  # 全部重翻
  python translate_with_glm.py --model glm-4-plus --files text_chunk_001.json
"""

import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# 项目内 Memori 与 instruction 路径
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
MEMORI_PATH = SCRIPT_DIR / "debug" / "memori.json"

# 默认使用智谱 OpenAI 兼容 API（GLM-4 系列），配置从 .env 读取
DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
DEFAULT_MODEL = "glm-4-plus"  # 可选 glm-4, glm-4-plus 等

# 逐条翻译，每轮请求只发一条；对话历史只保留最近 N 轮，避免上下文过长
MAX_HISTORY_TURNS = 10  # 保留最近 10 轮（每轮 = user + assistant）

# Memori 作为 tool 暴露给模型，按需调用检索词条，不把 hits 塞进 prompt
MEMORI_TOOL = {
    "type": "function",
    "function": {
        "name": "memori_search",
        "description": "从术语库（Memori）中按关键词检索日文→中文译法。翻译前若需要统一专有名词、忍术名、角色名、菜单项等可调用此工具，传入日文片段或中文关键词。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索关键词（日文或中文片段）"},
            },
            "required": ["query"],
        },
    },
}


def get_client() -> OpenAI:
    api_key = os.environ.get("GLM_API_KEY") or os.environ.get("ZHIPU_API_KEY")
    if not api_key:
        print("请在 .env 中设置 GLM_API_KEY 或 ZHIPU_API_KEY（智谱 API Key）", file=sys.stderr)
        sys.exit(1)
    base_url = os.environ.get("GLM_BASE_URL", DEFAULT_BASE_URL)
    return OpenAI(api_key=api_key, base_url=base_url)


def load_instruction() -> str:
    if not INSTRUCTION_PATH.exists():
        raise FileNotFoundError(f"未找到 {INSTRUCTION_PATH}")
    return INSTRUCTION_PATH.read_text(encoding="utf-8")


def load_memori():
    from memori_store import MemoriStore
    return MemoriStore(MEMORI_PATH)


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
    memori,
) -> tuple[dict, list[dict]]:
    """发送单条条目翻译，返回 (单条结果, 更新后的 messages)。Memori 通过 tool 按需调用，不注入 prompt。"""
    inputs = to_instruction_input(entry)
    user_content = "请将以下 JSON 数组中的日文翻译成中文（仅输出 JSON 数组，不要其他说明）：\n"
    user_content += json.dumps(inputs, ensure_ascii=False, indent=2)

    messages = _truncate_messages(messages)
    new_messages = messages + [{"role": "user", "content": user_content}]
    offset = entry["offset"]
    orig = entry["original"]
    out: dict = {"offset": offset, "text": orig, "skiped": False}

    while True:
        resp = client.chat.completions.create(
            model=model,
            messages=new_messages,
            tools=[MEMORI_TOOL],
            temperature=0.3,
        )
        choice = resp.choices[0] if resp.choices else None
        if not choice:
            return out, new_messages
        msg = getattr(choice, "message", None)
        if not msg:
            return out, new_messages

        content = (msg.content or "").strip()
        tool_calls = getattr(msg, "tool_calls", None) or []

        # 将本轮 assistant 回复追加到对话
        assistant_msg = {"role": "assistant", "content": content or ""}
        if tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments or "{}",
                    },
                }
                for tc in tool_calls
            ]
        new_messages = new_messages + [assistant_msg]

        if not tool_calls:
            break

        # 执行 tool 调用并追加 tool 结果
        for tc in tool_calls:
            name = getattr(tc.function, "name", "") if hasattr(tc, "function") else ""
            args_str = getattr(tc.function, "arguments", "{}") if hasattr(tc, "function") else "{}"
            try:
                args = json.loads(args_str) if args_str else {}
            except json.JSONDecodeError:
                args = {}
            query = args.get("query", "").strip()
            if name == "memori_search":
                result = memori.search(query)
                tool_content = json.dumps(result, ensure_ascii=False)
            else:
                tool_content = json.dumps({"error": "unknown tool"})
            new_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_content,
            })

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
    memori,
    all_entries: list[dict],
    *,
    skip_filled: bool = True,
    dry_run: bool = False,
) -> None:
    """对所有条目统一循环、逐条翻译，结果写入唯一输出文件 translate/translations.json。"""
    # 从唯一输出文件合并已有 translation/skiped
    if skip_filled:
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
        if "original" in e and (not skip_filled or not (e.get("translation") or "").strip())
    ]

    if not to_translate:
        print(f"  无需翻译（共 {len(all_entries)} 条）")
        return

    print(f"  待翻译 {len(to_translate)} / {len(all_entries)} 条（合并 chunk 逐条翻译，Memori 按需 tool 调用）")
    if dry_run:
        return

    # 不再把 hits 注入 prompt；system 只放 instruction + 工具说明，模型通过 memori_search tool 按需查词
    system = instruction + "\n\n如需查阅术语译法（角色名、忍术、菜单等），请调用 memori_search 工具传入关键词后再翻译。"
    messages = [{"role": "system", "content": system}]

    total_items = len(to_translate)
    offset_to_entry = {e["offset"]: e for e in all_entries}
    for idx, entry in enumerate(to_translate, start=1):
        try:
            r, messages = translate_one(client, model, messages, entry, memori)
            ent = offset_to_entry.get(r["offset"])
            if ent is not None:
                ent["translation"] = r["text"]
                ent["skiped"] = r.get("skiped", False)
            save_translations_file(all_entries, skip_filled=skip_filled)  # 每条翻译后立即写回；skip_filled 时连 skiped 的也更新 original/hex
            print(f"    已翻译 {idx}/{total_items} 条")
        except Exception as exc:
            print(f"    第 {idx} 条失败: {exc}", file=sys.stderr)
            raise

    print(f"  已写入 {TRANSLATIONS_OUTPUT_PATH}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="使用 GLM-4 + Memori 翻译 text_dump 下的 JSON")
    parser.add_argument(
        "--model",
        default=os.environ.get("GLM_MODEL", DEFAULT_MODEL),
        help="模型名（也可在 .env 中设置 GLM_MODEL）",
    )
    parser.add_argument("--no-skip", action="store_true", help="不跳过已有 translation 的条目，全部重翻")
    parser.add_argument("--dry-run", action="store_true", help="只列出待翻译文件与条数，不请求 API")
    parser.add_argument("--files", nargs="*", help="仅处理这些 chunk 文件（例如 text_chunk_001.json）")
    args = parser.parse_args()

    instruction = load_instruction()
    memori = load_memori()
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

    print(f"Memori 路径: {MEMORI_PATH}")
    print(f"输出文件: {TRANSLATIONS_OUTPUT_PATH}")
    print(f"已合并 chunk 数: {len(files)}，总条数: {len(all_entries)}")
    process_all(
        client,
        args.model,
        instruction,
        memori,
        all_entries,
        skip_filled=not args.no_skip,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
