#!/usr/bin/env python3
"""
NDS RPG3 汉化补丁：解压 ROM → 从 translate/rpg3 的 JSON 生成 8x8/8x16 码表与字模并追加到 data/font →
按新码表写入 overlay 与 data/text 译文 → 打包回 ROM。
"""
import importlib.util
import json
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import click

SCRIPT_DIR = Path(__file__).resolve().parent
PYTHON_DIR = SCRIPT_DIR
DEBUG_DIR = PYTHON_DIR / "debug"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

# 默认 JSON 目录：../translate/rpg3，不存在则用 debug/rpg3
DEFAULT_JSON_DIR = (PYTHON_DIR / ".." / "translate" / "rpg3").resolve()
FALLBACK_JSON_DIR = PYTHON_DIR / "debug" / "rpg3"
# 预置二进制：overlay_0000.bin、arm9.bin 从此目录覆盖到解压目录（优先 python/rpg3binary，否则仓库根/rpg3binary）
def _rpg3_binary_dir() -> Path | None:
    d = PYTHON_DIR / "rpg3binary"
    if d.is_dir():
        return d
    d = (PYTHON_DIR / ".." / "rpg3binary").resolve()
    return d if d.is_dir() else None

BYTES_PER_CHAR_8x8 = 0x20
BYTES_PER_CHAR_8x16 = 0x40
FULL_WIDTH_SPACE = "　"
SPACE_ROM_BYTES = bytes([0x81, 0x40])


def _load_font_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, DEBUG_DIR / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _render_8x8(chars: list[str], font_path_8x8: Path) -> bytes:
    mod = _load_font_module("font_8x8", "8x8_font.py")
    import freetype
    face = freetype.Face(str(font_path_8x8))
    out = bytearray()
    for ch in chars:
        px, w, h = mod.ft_render_mono(face, ch, px_size=8)
        tile = mod.px_to_tile_8x8(px, w, h)
        out += mod.tile01_to_gba4bpp(tile)
    return bytes(out)


def _render_8x16(
    chars: list[str],
    font_path_8x16: Path,
    scale_8x16_mode: str = "none",
) -> bytes:
    mod = _load_font_module("font_8x16", "8x16_font.py")
    import freetype
    face = freetype.Face(str(font_path_8x16))
    out = bytearray()
    use_8x12 = scale_8x16_mode in ("scale", "pad")
    for ch in chars:
        if use_8x12:
            px, w, h = mod.ft_render_mono(face, ch, cell_size=(8, 12))
            g8x12 = mod.blit_center(px, w, h, 8, 12)
            g8x16 = mod.scale_8x12_to_8x16(g8x12) if scale_8x16_mode == "scale" else mod.pad_8x12_to_8x16(g8x12)
        else:
            px, w, h = mod.ft_render_mono(face, ch, px_size=16)
            canvas16 = mod.blit_center(px, w, h, 16, 16)
            g8x16 = mod.compress_16w_to_8w(canvas16, mode="or")
        out += mod.glyph8x16_to_gba4bpp(g8x16)
    return bytes(out)


def _get_last_key_from_tbl(tbl_path: Path) -> int:
    """读取 tbl 中最后一个条目的 key（小端 u16），若文件为空或不存在返回 -1。"""
    if not tbl_path.is_file():
        return -1
    data = tbl_path.read_bytes()
    if len(data) < 4:
        return -1
    n = len(data) // 4
    key_lo, key_hi = data[(n - 1) * 4], data[(n - 1) * 4 + 1]
    return key_lo | (key_hi << 8)


def _append_font_and_tbl(
    extract_dir: Path,
    chars: list[str],
    font_path_8x8: Path,
    font_path_8x16: Path,
    scale_8x16_mode: str,
    write_tbl: bool = True,
    write_chr: bool = True,
    write_1x1: bool = True,
    write_1x2: bool = True,
    max_chars_chr: int | None = None,
    max_chars_tbl: int | None = None,
) -> tuple[dict[str, int], int, int, int]:
    """
    向 extract_dir/data/font 追加 8x8/8x16 字模与/或码表。
    max_chars_chr: 仅前 N 字写入 chr；max_chars_tbl: 仅前 N 字写入 tbl。mapping 始终含全部 chars。
    返回 (mapping, font_1x1_last_key, n_chr_written, n_tbl_written)。
    """
    font_dir = extract_dir / "data" / "font"
    font_dir.mkdir(parents=True, exist_ok=True)
    chr_1x1 = font_dir / "font_1x1.chr"
    chr_1x2 = font_dir / "font_1x2.chr"
    tbl_1x1 = font_dir / "font_1x1.tbl"
    tbl_1x2 = font_dir / "font_1x2.tbl"

    for p in (chr_1x1, chr_1x2, tbl_1x1, tbl_1x2):
        if not p.exists():
            p.write_bytes(b"")

    last_key_1x2 = _get_last_key_from_tbl(tbl_1x2)
    first_new_key = last_key_1x2 + 1

    len_1x1 = chr_1x1.stat().st_size
    tile_count_8x8 = len_1x1 // BYTES_PER_CHAR_8x8
    # 1x2 chr 从 0x40 处开始写，对应 tile 索引为 0x40 // 0x40 = 1
    OFFSET_1X2_CHR = 0x40
    tile_base_8x16 = OFFSET_1X2_CHR // BYTES_PER_CHAR_8x16

    chars_for_chr = chars[:max_chars_chr] if max_chars_chr is not None and max_chars_chr > 0 else chars
    chars_for_tbl = chars[:max_chars_tbl] if max_chars_tbl is not None and max_chars_tbl > 0 else chars

    if write_chr and write_1x1:
        data_8x8 = _render_8x8(chars_for_chr, font_path_8x8)
    else:
        data_8x8 = b""
    if write_chr and write_1x2:
        data_8x16 = _render_8x16(chars_for_chr, font_path_8x16, scale_8x16_mode=scale_8x16_mode)
    else:
        data_8x16 = b""

    mapping: dict[str, int] = {}
    for i, ch in enumerate(chars):
        mapping[ch] = (first_new_key + i) & 0xFFFF

    tbl_append_1x1 = bytearray()
    tbl_append_1x2 = bytearray()
    for i, ch in enumerate(chars_for_tbl):
        key = first_new_key + i
        val_8x8 = tile_count_8x8 + i
        val_8x16 = tile_base_8x16 + i
        tbl_append_1x1 += struct.pack("<HH", key & 0xFFFF, val_8x8 & 0xFFFF)
        tbl_append_1x2 += struct.pack("<HH", key & 0xFFFF, val_8x16 & 0xFFFF)

    if write_chr and write_1x1:
        with open(chr_1x1, "ab") as f:
            f.write(data_8x8)
    if write_chr and write_1x2:
        existing_1x2 = chr_1x2.read_bytes()
        head = (existing_1x2[:OFFSET_1X2_CHR] if len(existing_1x2) >= OFFSET_1X2_CHR else existing_1x2).ljust(OFFSET_1X2_CHR, b"\x00")
        chr_1x2.write_bytes(head + data_8x16)
    if write_tbl and write_1x1:
        with open(tbl_1x1, "ab") as f:
            f.write(tbl_append_1x1)
    if write_tbl and write_1x2:
        with open(tbl_1x2, "ab") as f:
            f.write(tbl_append_1x2)

    font_1x1_last_key = first_new_key + len(chars) - 1 if chars else last_key_1x2
    n_chr_written = len(chars_for_chr)
    n_tbl_written = len(chars_for_tbl)
    return mapping, font_1x1_last_key, n_chr_written, n_tbl_written


def _take_chars_from_entries(entries: list[dict]) -> list[str]:
    """从 overlay/text 条目中收集译文里出现的可打印字符（去重排序）。空格不收集，编码时固定用 0x8140。"""
    chars = set()
    for entry in entries:
        trans = entry.get("translation") or ""
        if not trans:
            continue
        for ch in trans:
            if not ch.isprintable():
                continue
            if ch in (" ", FULL_WIDTH_SPACE):
                continue
            chars.add(ch)
    return sorted(chars)


def _translation_to_fixed_length(translation: str, original: str) -> str:
    """译文按原文长度对齐：不足用全角空格（0x8140）右填充，过长截断。"""
    orig_len = len(original)
    s = (translation or "").strip()
    if len(s) >= orig_len:
        return s[:orig_len]
    return s + FULL_WIDTH_SPACE * (orig_len - len(s))


def _encode_char_nds(ch: str, mapping: dict[str, int]) -> bytes:
    """单字编码：空格 0x8140，在 mapping 中为 key 大端 2 字节，否则 Shift-JIS。"""
    if ch in (" ", FULL_WIDTH_SPACE):
        return SPACE_ROM_BYTES
    if ch in mapping:
        return struct.pack(">H", mapping[ch] & 0xFFFF)
    return ch.encode("shift_jis", errors="replace")[:2].ljust(2, b"\x00")


def _encode_translation_nds(text: str, mapping: dict[str, int]) -> bytes:
    out = bytearray()
    for ch in text:
        out += _encode_char_nds(ch, mapping)
    return bytes(out)


def _parse_offset(offset: str | int) -> int:
    if isinstance(offset, int):
        return offset
    s = str(offset).strip()
    if s.startswith("0x") or s.startswith("0X"):
        return int(s, 16)
    return int(s, 10)


def _apply_translations(
    extract_dir: Path,
    overlay_entries: list[dict],
    text_entries: list[dict],
    mapping: dict[str, int],
    only_src: str = "both",
) -> dict[str, int]:
    """only_src: 'both' | 'overlay' | 'text'，只写入指定来源的译文。返回 {相对路径: 写入条数}。"""
    overlay_base = extract_dir / "overlay"
    text_base = extract_dir / "data" / "text"
    modified: dict[str, int] = {}

    if only_src not in ("overlay", "text"):
        only_src = "both"
    do_overlay = only_src in ("both", "overlay")
    do_text = only_src in ("both", "text")

    if do_overlay:
        for entry in overlay_entries:
            if entry.get("skiped"):
                continue
            trans = entry.get("translation") or ""
            if not trans:
                continue
            orig = entry.get("original", "")
            s = _translation_to_fixed_length(trans, orig)
            offset = _parse_offset(entry["offset"])
            file_name = entry.get("file", "").replace("\\", "/")
            target = overlay_base / file_name
            if not target.is_file():
                continue
            encoded = _encode_translation_nds(s, mapping)
            with open(target, "r+b") as f:
                f.seek(offset)
                f.write(encoded)
            rel = str(Path("overlay") / file_name)
            modified[rel] = modified.get(rel, 0) + 1

    if do_text:
        for entry in text_entries:
            if entry.get("skiped"):
                continue
            trans = entry.get("translation") or ""
            if not trans:
                continue
            orig = entry.get("original", "")
            s = _translation_to_fixed_length(trans, orig)
            offset = _parse_offset(entry["offset"])
            file_name = entry.get("file", "").replace("\\", "/")
            target = text_base / file_name
            if not target.is_file():
                continue
            encoded = _encode_translation_nds(s, mapping)
            with open(target, "r+b") as f:
                f.seek(offset)
                f.write(encoded)
            rel = str(Path("data") / "text" / file_name)
            modified[rel] = modified.get(rel, 0) + 1

    return modified


def _apply_rpg3_binary(extract_dir: Path) -> None:
    """将 rpg3binary/overlay_0000.bin 覆盖到解压目录/overlay/，rpg3binary/arm9.bin 覆盖到解压目录/。"""
    bin_dir = _rpg3_binary_dir()
    if bin_dir is None:
        click.echo("未找到 rpg3binary 目录（python/rpg3binary 或 仓库根/rpg3binary），跳过预置二进制覆盖。")
        return
    overlay_src = bin_dir / "overlay_0000.bin"
    overlay_dst_dir = extract_dir / "overlay"
    overlay_dst = overlay_dst_dir / "overlay_0000.bin"
    if overlay_src.is_file():
        overlay_dst_dir.mkdir(parents=True, exist_ok=True)
        overlay_dst.write_bytes(overlay_src.read_bytes())
        click.echo(f"已覆盖 overlay：{overlay_src} → {overlay_dst}")
    else:
        click.echo(f"未找到 {overlay_src}，跳过 overlay 覆盖。")
    # arm9_src = bin_dir / "arm9.bin"
    # arm9_dst = extract_dir / "arm9.bin"
    # if arm9_src.is_file():
    #     arm9_dst.write_bytes(arm9_src.read_bytes())
    #     click.echo(f"已覆盖 arm9：{arm9_src} → {arm9_dst}")
    # else:
    #     click.echo(f"未找到 {arm9_src}，跳过 arm9 覆盖。")


def _run_nds_extract(rom_path: Path, output_dir: Path, verbose: bool = False) -> None:
    cmd = [sys.executable, str(DEBUG_DIR / "nds_extract.py"), str(rom_path.resolve()), "-o", str(output_dir)]
    if verbose:
        cmd.append("-v")
    r = subprocess.run(cmd, cwd=str(PYTHON_DIR))
    if r.returncode != 0:
        raise SystemExit(r.returncode)


def _run_nds_pack(input_dir: Path, output_rom: Path, verbose: bool = False) -> None:
    cmd = [sys.executable, str(DEBUG_DIR / "nds_pack.py"), str(input_dir), "-o", str(output_rom)]
    if verbose:
        cmd.append("-v")
    r = subprocess.run(cmd, cwd=str(PYTHON_DIR))
    if r.returncode != 0:
        raise SystemExit(r.returncode)


@click.command(
    help="解压 NDS ROM → 生成并追加 8x8/8x16 码表与字模 → 写入译文 → 打包回 ROM",
    epilog="""
示例:
  python patch_rpg3.py rom3.nds -o patched3.nds --font-8x8 debug/fusion-pixel-8px-monospaced-zh_hans.ttf --font-8x16 debug/MZPXflat.ttf --8x16-scale pad --temp-dir ./rpg3_patch
  python patch_rpg3.py rom3.nds -o patched.nds --font-8x8 font_8.ttf --font-8x16 font_16.ttf --8x16-scale pad
  python patch_rpg3.py rom3.nds -o patched.nds --font-8x8 font.ttf -m font_mapping.json
  python patch_rpg3.py rom3.nds -o patched.nds --font-8x8 font.ttf --font-write tbl
  python patch_rpg3.py rom3.nds -o patched.nds --font-8x8 font.ttf --font-write chr --font-size 1x2
  python patch_rpg3.py rom3.nds -o patched.nds --font-8x8 font.ttf --no-translation
  python patch_rpg3.py rom3.nds -o patched.nds --font-8x8 font.ttf --max-chars-chr 50 --max-chars-tbl 100
  python patch_rpg3.py rom3.nds -o patched.nds --debug
  python patch_rpg3.py rom3.nds -o patched3.nds --font-8x8 debug/fusion-pixel-8px-monospaced-zh_hans.ttf --font-8x16 debug/MZPXflat.ttf --8x16-scale pad --temp-dir ./rpg3_patch -m rpg3_mapping.json 
""",
)
@click.argument("rom", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", "out_rom", type=click.Path(path_type=Path), required=True, help="输出 ROM 路径")
@click.option("-m", "--out-mapping", "out_mapping", type=click.Path(path_type=Path), default=None, help="将字符→key 映射写入此 JSON，供后续使用")
@click.option("--temp-dir", type=click.Path(path_type=Path), default=None, help="解压临时目录（默认系统 temp）")
@click.option(
    "--json-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="overlay.json / text.json 所在目录（默认 ../translate/rpg3 或 debug/rpg3）",
)
@click.option("--font-8x8", "font_8x8", type=click.Path(exists=True, path_type=Path), default=None, help="8x8 字体 TTF（debug 时可省略）")
@click.option("--font-8x16", "font_8x16", type=click.Path(exists=True, path_type=Path), default=None, help="8x16 字体 TTF（不指定则用 8x8）")
@click.option(
    "--8x16-scale",
    "scale_8x16",
    type=click.Choice(["none", "scale", "pad"], case_sensitive=False),
    default="pad",
    help="8x16 字模：none/scale/pad",
)
@click.option(
    "--only",
    "only_src",
    type=click.Choice(["text", "overlay", "both"], case_sensitive=False),
    default="both",
    help="只导入 text / 只导入 overlay / 两者都导入（默认 both）",
)
@click.option(
    "--font-write",
    "font_write",
    type=click.Choice(["both", "tbl", "chr"], case_sensitive=False),
    default="both",
    help="只写码表(tbl) / 只写字模(chr) / 两者都写（默认 both）",
)
@click.option(
    "--font-size",
    "font_size",
    type=click.Choice(["both", "1x1", "1x2"], case_sensitive=False),
    default="both",
    help="只写 1x1(8x8) / 只写 1x2(8x16) / 两者都写（默认 both）",
)
@click.option("--no-translation", "no_translation", is_flag=True, help="不写入 overlay/text 译文，仅更新码表与字模")
@click.option("--max-chars-chr", "max_chars_chr", type=int, default=None, help="chr 字模上限（调试用）：仅前 N 字写入 chr，超出不写字模")
@click.option("--max-chars-tbl", "max_chars_tbl", type=int, default=None, help="tbl 码表上限（调试用）：仅前 N 字写入 tbl，超出不写码表条目；译文仍用全部字编码")
@click.option("--debug", "debug_mode", is_flag=True, help="debug：仅解压后打包，不写码表/字模/译文")
@click.option("-v", "--verbose", is_flag=True, help="解压/打包时显示详细信息")
def main(
    rom: Path,
    out_rom: Path,
    out_mapping: Path | None,
    temp_dir: Path | None,
    json_dir: Path | None,
    font_8x8: Path | None,
    font_8x16: Path | None,
    scale_8x16: str,
    only_src: str,
    font_write: str,
    font_size: str,
    no_translation: bool,
    max_chars_chr: int | None,
    max_chars_tbl: int | None,
    debug_mode: bool,
    verbose: bool,
) -> None:
    rom = rom.resolve()
    out_rom = out_rom.resolve()

    if temp_dir is None:
        tmp = tempfile.mkdtemp(prefix="nds_rpg3_patch_")
        extract_dir = Path(tmp)
        do_cleanup = True
    else:
        extract_dir = temp_dir.resolve()
        extract_dir.mkdir(parents=True, exist_ok=True)
        do_cleanup = False

    try:
        if debug_mode:
            click.echo("debug 模式：仅解压后打包，不写码表/字模/译文。")
            click.echo(f"解压 ROM 到 {extract_dir} ...")
            _run_nds_extract(rom, extract_dir, verbose=verbose)
            out_rom.parent.mkdir(parents=True, exist_ok=True)
            click.echo(f"打包到 {out_rom} ...")
            _run_nds_pack(extract_dir, out_rom, verbose=verbose)
            click.echo("完成")
            if do_cleanup and extract_dir.exists():
                shutil.rmtree(extract_dir, ignore_errors=True)
                click.echo("已删除临时目录")
            return

        if font_8x8 is None:
            raise SystemExit("非 debug 模式必须指定 --font-8x8")
        font_16 = font_8x16 if font_8x16 is not None else font_8x8

        if json_dir is None:
            json_dir = DEFAULT_JSON_DIR if DEFAULT_JSON_DIR.is_dir() else FALLBACK_JSON_DIR
        if not json_dir.is_dir():
            raise SystemExit(f"JSON 目录不存在: {json_dir}")

        overlay_path = json_dir / "overlay.json"
        text_path = json_dir / "text.json"
        if not overlay_path.is_file():
            raise SystemExit(f"缺少 {overlay_path}")
        if not text_path.is_file():
            raise SystemExit(f"缺少 {text_path}")

        with open(overlay_path, "r", encoding="utf-8") as f:
            overlay_data = json.load(f)
        with open(text_path, "r", encoding="utf-8") as f:
            text_data = json.load(f)

        only_src = only_src.lower()
        if only_src == "overlay":
            all_entries = overlay_data
        elif only_src == "text":
            all_entries = text_data
        else:
            all_entries = overlay_data + text_data
        chars = _take_chars_from_entries(all_entries)
        click.echo(f"从 JSON 收集到 {len(chars)} 个扩展字符")

        if max_chars_chr is not None or max_chars_tbl is not None:
            n_chr_limit = len(chars[:max_chars_chr]) if max_chars_chr and max_chars_chr > 0 else len(chars)
            n_tbl_limit = len(chars[:max_chars_tbl]) if max_chars_tbl and max_chars_tbl > 0 else len(chars)
            click.echo(f"上限：chr 前 {n_chr_limit} 字，tbl 前 {n_tbl_limit} 字；全部 {len(chars)} 字参与译文编码")

        if not chars:
            click.echo("没有需要追加的字符，仅解压、写入现有译文、打包。")

        click.echo(f"解压 ROM 到 {extract_dir} ...")
        _run_nds_extract(rom, extract_dir, verbose=verbose)
        _apply_rpg3_binary(extract_dir)

        mapping: dict[str, int] = {}
        font_1x1_last_key = -1
        if chars:
            write_tbl = font_write.lower() in ("both", "tbl")
            write_chr = font_write.lower() in ("both", "chr")
            write_1x1 = font_size.lower() in ("both", "1x1")
            write_1x2 = font_size.lower() in ("both", "1x2")
            mapping, font_1x1_last_key, n_chr_written, n_tbl_written = _append_font_and_tbl(
                extract_dir, chars, font_8x8, font_16, scale_8x16,
                write_tbl=write_tbl, write_chr=write_chr,
                write_1x1=write_1x1, write_1x2=write_1x2,
                max_chars_chr=max_chars_chr, max_chars_tbl=max_chars_tbl,
            )
            click.echo(f"font_1x1 最后 key（小端序）= {font_1x1_last_key} (0x{font_1x1_last_key:X})")
            if write_tbl:
                if write_1x1 and write_1x2:
                    click.echo(f"码表：font_1x1.tbl / font_1x2.tbl 各追加 {n_tbl_written} 条（每条 4 字节，共 {n_tbl_written * 4 * 2} 字节）")
                elif write_1x1:
                    click.echo(f"码表：font_1x1.tbl 追加 {n_tbl_written} 条（{n_tbl_written * 4} 字节）")
                else:
                    click.echo(f"码表：font_1x2.tbl 追加 {n_tbl_written} 条（{n_tbl_written * 4} 字节）")
            if write_chr:
                if write_1x1 and write_1x2:
                    click.echo(f"字模：font_1x1.chr 追加 {n_chr_written} 字（{n_chr_written * BYTES_PER_CHAR_8x8} 字节），font_1x2.chr 追加 {n_chr_written} 字（{n_chr_written * BYTES_PER_CHAR_8x16} 字节）")
                elif write_1x1:
                    click.echo(f"字模：font_1x1.chr 追加 {n_chr_written} 字（{n_chr_written * BYTES_PER_CHAR_8x8} 字节）")
                else:
                    click.echo(f"字模：font_1x2.chr 追加 {n_chr_written} 字（{n_chr_written * BYTES_PER_CHAR_8x16} 字节）")

        if out_mapping is not None:
            with open(out_mapping, "w", encoding="utf-8") as f:
                json.dump(mapping, f, ensure_ascii=False, indent=2)
            click.echo(f"字符→key 映射已写入 {out_mapping}")

        if no_translation:
            click.echo("已跳过写入译文（--no-translation）。")
        else:
            modified = _apply_translations(extract_dir, overlay_data, text_data, mapping, only_src=only_src)
            total_entries = sum(modified.values())
            click.echo("已按新码表写入 overlay 与 data/text 译文" if only_src == "both" else f"已按新码表写入 {'overlay' if only_src == 'overlay' else 'data/text'} 译文")
            if modified:
                click.echo(f"共修改 {len(modified)} 个文件，{total_entries} 处译文：")
                for rel in sorted(modified.keys()):
                    click.echo(f"  {rel}: {modified[rel]} 处")
            else:
                click.echo("未写入任何译文（无有效条目或未命中文件）。")

        out_rom.parent.mkdir(parents=True, exist_ok=True)
        click.echo(f"打包到 {out_rom} ...")
        _run_nds_pack(extract_dir, out_rom, verbose=verbose)
        click.echo("完成")
        if do_cleanup and extract_dir.exists():
            shutil.rmtree(extract_dir, ignore_errors=True)
            click.echo("已删除临时目录")
    except Exception:
        if do_cleanup and extract_dir.exists():
            shutil.rmtree(extract_dir, ignore_errors=True)
        raise


if __name__ == "__main__":
    main()
