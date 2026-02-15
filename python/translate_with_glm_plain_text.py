#!/usr/bin/env python3
"""
纯文本批量翻译：输入/输出均按 \\n 分割，每批 N 条一次请求，严格一一对应。
使用 translate_plain.instruction.md；跳过条在对应行输出 SKIPED，脚本据此写回原文。
与 translate_with_glm.py 共用 .env、translations.json，不依赖 Memori 工具。

使用：
  python translate_with_glm_plain_text.py              # 每批 500 条，跳过已有译文
  python translate_with_glm_plain_text.py --batch-size 200
  python translate_with_glm_plain_text.py --dry-run
  python translate_with_glm_plain_text.py --no-skip --files text_chunk_001.json
"""

import os
import sys
from pathlib import Path

# 复用原脚本的配置与读写
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from translate_with_glm import (
    get_client,
    list_chunk_files,
    load_all_entries,
    load_translations_file,
    save_translations_file,
    align_length,
    TRANSLATIONS_OUTPUT_PATH,
    TEXT_DUMP_DIR,
    DEFAULT_MODEL,
)

# 纯文本批量专用 instruction
INSTRUCTION_PLAIN_PATH = SCRIPT_DIR / "translate_plain.instruction.md"
# 批量大小与空行占位
BATCH_SIZE = 500
PLACEHOLDER_EMPTY = "(空)"
SKIPED_MARKER = "SKIPED"


def _normalize_line(text: str) -> str:
    """将一条原文规范为单行（用于批量输入），便于按 \\n 严格对应。"""
    if text is None:
        return PLACEHOLDER_EMPTY
    s = (text or "").replace("\r", " ").replace("\n", " ").strip()
    return s if s else PLACEHOLDER_EMPTY


def translate_batch(client, model: str, instruction: str, entries_batch: list[dict]) -> list[str]:
    """批量翻译：输入多行纯文本（每行一条），输出多行纯文本，按 \\n 分割严格一一对应。
    返回与 entries_batch 等长的译文列表；若模型返回行数不一致则用原文补齐或截断。
    """
    if not entries_batch:
        return []
    lines_in = [_normalize_line(e.get("original", "")) for e in entries_batch]
    input_text = "\n".join(lines_in)
    system = (
        instruction
        + "\n\n【批量模式】下面将收到多行日文，每行一条。"
        "请只输出相同行数的结果，严格按行顺序一一对应，每行一条，不要编号、不要空行、不要合并。"
        "若某条属于职员表/报幕等不翻译内容，请在该行只输出 SKIPED（全大写）。不要输出任何解释。"
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": input_text},
        ],
        temperature=0.3,
    )
    content = (resp.choices[0].message.content or "").strip()
    out_lines = [ln.strip() for ln in content.split("\n")]
    n = len(entries_batch)
    if len(out_lines) < n:
        for i in range(len(out_lines), n):
            out_lines.append(_normalize_line(entries_batch[i].get("original", "")))
    elif len(out_lines) > n:
        out_lines = out_lines[:n]
    return out_lines


def process_all_plain_text(
    client,
    model: str,
    instruction: str,
    all_entries: list[dict],
    *,
    batch_size: int = BATCH_SIZE,
    skip_filled: bool = True,
    dry_run: bool = False,
) -> None:
    """按批调用纯文本翻译，结果写回 translate/translations.json。"""
    # 始终加载已有结果，用于合并 translation/skiped；--no-skip 时也需据此排除已 skip 的条
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

    # 待翻译：有 original 且（未填译文 或 --no-skip 重翻）；但已标记 skiped 的条始终不重发
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

    print(f"  待翻译 {len(to_translate)} / {len(all_entries)} 条（纯文本批量，每批 {batch_size} 条）")
    if dry_run:
        return

    offset_to_entry = {e["offset"]: e for e in all_entries}
    num_batches = (len(to_translate) + batch_size - 1) // batch_size
    for b in range(num_batches):
        start = b * batch_size
        chunk = to_translate[start : start + batch_size]
        try:
            out_lines = translate_batch(client, model, instruction, chunk)
        except Exception as exc:
            print(f"  第 {b + 1}/{num_batches} 批失败: {exc}", file=sys.stderr)
            raise
        for i, entry in enumerate(chunk):
            trans_line = out_lines[i] if i < len(out_lines) else _normalize_line(entry.get("original", ""))
            orig = (entry.get("original") or "")
            is_skiped = trans_line.strip().upper() == SKIPED_MARKER or (
                not orig.strip() and trans_line.strip() in ("", PLACEHOLDER_EMPTY)
            )
            ent = offset_to_entry.get(entry["offset"])
            if ent is not None:
                if is_skiped:
                    ent["translation"] = orig
                else:
                    ent["translation"] = align_length(trans_line, ent["original"])
                ent["skiped"] = is_skiped
        save_translations_file(all_entries, skip_filled=skip_filled)
        print(f"    已翻译第 {b + 1}/{num_batches} 批（本批 {len(chunk)} 条）")
    print(f"  已写入 {TRANSLATIONS_OUTPUT_PATH}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="纯文本批量翻译 text_dump 下的 JSON（按 \\n 对应）")
    parser.add_argument(
        "--model",
        default=os.environ.get("GLM_MODEL", DEFAULT_MODEL),
        help="模型名",
    )
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help=f"每批条数（默认 {BATCH_SIZE}）")
    parser.add_argument("--no-skip", action="store_true", help="不跳过已有译文，全部重翻")
    parser.add_argument("--dry-run", action="store_true", help="只列待翻译条数，不请求 API")
    parser.add_argument("--files", nargs="*", help="仅处理这些 chunk 文件")
    args = parser.parse_args()

    if not INSTRUCTION_PLAIN_PATH.exists():
        print(f"未找到 {INSTRUCTION_PLAIN_PATH}", file=sys.stderr)
        return
    instruction = INSTRUCTION_PLAIN_PATH.read_text(encoding="utf-8")
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

    print(f"Instruction: {INSTRUCTION_PLAIN_PATH}")
    print(f"输出文件: {TRANSLATIONS_OUTPUT_PATH}")
    print(f"已合并 chunk 数: {len(files)}，总条数: {len(all_entries)}")
    process_all_plain_text(
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
