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
INSTRUCTION_PATH = SCRIPT_DIR / "translate.instruction.md"
MEMORI_PATH = SCRIPT_DIR / "debug" / "memori.json"

# 默认使用智谱 OpenAI 兼容 API（GLM-4 系列），配置从 .env 读取
DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
DEFAULT_MODEL = "glm-4-plus"  # 可选 glm-4, glm-4-plus 等

# 每批条数，避免单次请求过长
BATCH_SIZE = 25


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


def to_instruction_input(batch: list[dict]) -> list[dict]:
    """转换为 instruction 规定的输入格式：仅含 offset、text 的 JSON 数组。"""
    return [{"offset": e["offset"], "text": e["original"]} for e in batch]


def translate_batch_in_conversation(
    client: OpenAI,
    model: str,
    messages: list[dict],
    batch: list[dict],
) -> tuple[list[dict], list[dict]]:
    """在同一对话内发送本批条目，返回 (本批结果, 更新后的 messages)。"""
    # 严格按 instruction 输入格式：[{ "offset": "0x...", "text": "日文" }]
    inputs = to_instruction_input(batch)
    user_content = "请将以下 JSON 数组中的日文翻译成中文（仅输出 JSON 数组，不要其他说明）：\n"
    user_content += json.dumps(inputs, ensure_ascii=False, indent=2)

    new_messages = messages + [{"role": "user", "content": user_content}]
    stream = client.chat.completions.create(
        model=model,
        messages=new_messages,
        temperature=0.3,
        stream=True,
    )
    content_parts = []
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if getattr(delta, "content", None):
            content_parts.append(delta.content)
            print(delta.content, end="", flush=True)
    print(flush=True)  # 流式输出后换行
    content = "".join(content_parts).strip()
    if not content:
        return [], new_messages
    out_list = extract_json_array(content)
    by_offset = {str(item.get("offset", "")): item.get("text", "") for item in out_list}
    result = []
    for e in batch:
        offset = e["offset"]
        orig = e["original"]
        trans = by_offset.get(offset, "")
        trans = align_length(trans, orig)
        result.append({"offset": offset, "text": trans})
    # 把本轮 assistant 回复追加到对话，下一批会带上这段历史
    updated = new_messages + [{"role": "assistant", "content": content}]
    return result, updated


def process_file(
    client: OpenAI,
    model: str,
    instruction: str,
    memori,
    path: Path,
    *,
    skip_filled: bool = True,
    dry_run: bool = False,
) -> None:
    """处理单个 chunk JSON 文件：从源文件读取，翻译结果写入项目目录/translate/，不修改源文件。"""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        print(f"  [{path.name}] 格式错误，跳过", file=sys.stderr)
        return

    entries = [e for e in raw if isinstance(e, dict)]
    # 若已有输出文件，先合并其中的 translation，用于 skip_filled 时跳过已译
    output_path = OUTPUT_DIR / path.name
    if skip_filled and output_path.exists():
        try:
            out_data = json.loads(output_path.read_text(encoding="utf-8"))
            if isinstance(out_data, list):
                by_offset = {e.get("offset"): e.get("translation", "") for e in out_data if isinstance(e, dict)}
                for e in entries:
                    if e.get("offset") in by_offset and by_offset[e["offset"]]:
                        e["translation"] = by_offset[e["offset"]]
        except (json.JSONDecodeError, IOError):
            pass

    to_translate = [
        e
        for e in entries
        if "original" in e and (not skip_filled or not (e.get("translation") or "").strip())
    ]
    if not to_translate:
        print(f"  [{path.name}] 无需翻译（共 {len(entries)} 条）")
        return

    print(f"  [{path.name}] 待翻译 {len(to_translate)} / {len(entries)} 条（同一对话内连续翻译）")
    if dry_run:
        return

    # 整份文件的术语一次性注入 system，后续批次在同一对话内沿用
    all_texts = [e["original"] for e in to_translate]
    memori_hits = memori.search_for_texts(all_texts).get("hits", [])
    system = instruction
    if memori_hits:
        system += "\n\n当前术语库（Memori）中与本文件相关的条目，请严格采用其中译法，并在后续批次中保持一致：\n"
        system += json.dumps(memori_hits, ensure_ascii=False, indent=2)
    messages = [{"role": "system", "content": system}]

    total_items = len(to_translate)
    total_batches = (total_items + BATCH_SIZE - 1) // BATCH_SIZE
    offset_to_entry = {e["offset"]: e for e in entries}
    for i in range(0, len(to_translate), BATCH_SIZE):
        batch = to_translate[i : i + BATCH_SIZE]
        batch_no = i // BATCH_SIZE + 1
        try:
            results, messages = translate_batch_in_conversation(client, model, messages, batch)
            for r in results:
                ent = offset_to_entry.get(r["offset"])
                if ent is not None:
                    ent["translation"] = r["text"]
            done = min(i + len(batch), total_items)
            print(f"    批次 {batch_no}/{total_batches} 完成，已翻译 {done}/{total_items} 条")
        except Exception as exc:
            print(f"    批次 {batch_no} 失败: {exc}", file=sys.stderr)
            raise

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [{path.name}] 已保存到 {output_path}")


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

    print(f"Memori 路径: {MEMORI_PATH}")
    print(f"输出目录: {OUTPUT_DIR}")
    print(f"待处理文件数: {len(files)}")
    for path in files:
        process_file(
            client,
            args.model,
            instruction,
            memori,
            path,
            skip_filled=not args.no_skip,
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    main()
