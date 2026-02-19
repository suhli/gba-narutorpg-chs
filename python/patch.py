import importlib.util
import json
import shutil
import struct
from pathlib import Path
from typing import Any

import click
import sys
SCRIPT_DIR = Path(__file__).resolve().parent.parent
PYTHON_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

TRANSLATIONS_FILE_PATH = SCRIPT_DIR / "translate" / "translations.json"
PREPATCH_FILE_PATH = PYTHON_DIR / "prepatch.json"
LAST_MAPPING_OFFSET_8x16 = 0xE5B0
LAST_MAPPING_OFFSET_8x8 = 0x97bd
LAST_FONT_OFFSET_8x16 = 0x300
LAST_FONT_OFFSET_8x8 = 0xE0
ENTRY_MAPPING_8x8 = 0x0061639C
ENTRY_MAPPING_8x16 = 0x004EB6CC
ENTRY_FONT_8x8 = 0x004B4900
ENTRY_FONT_8x16 = 0x00508900
LAST_8x8_COUNT = 0xCA
LAST_8x16_COUNT = 0x2BB
ENTRY_8x8_COUNT = 0x00616058
ENTRY_8x16_COUNT = 0x004EAB04

# 每字字节数：8x8 = 32 (0x20)，8x16 = 64 (0x40)
BYTES_PER_CHAR_8x8 = 0x20
BYTES_PER_CHAR_8x16 = 0x40


def _load_font_module(name: str, filename: str):
  spec = importlib.util.spec_from_file_location(name, PYTHON_DIR / "debug" / filename)
  mod = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(mod)
  return mod


def _render_8x8(chars: list[str], font_path_8x8: str | Path) -> bytes:
  mod = _load_font_module("font_8x8", "8x8_font.py")
  import freetype
  face = freetype.Face(str(font_path_8x8))
  out = bytearray()
  for ch in chars:
    px, w, h = mod.ft_render_mono(face, ch, px_size=8)
    tile = mod.px_to_tile_8x8(px, w, h)
    out += mod.tile01_to_gba4bpp(tile)
  return bytes(out)


def _render_8x16(chars: list[str], font_path_8x16: str | Path) -> bytes:
  mod = _load_font_module("font_8x16", "8x16_font.py")
  import freetype
  face = freetype.Face(str(font_path_8x16))
  out = bytearray()
  for ch in chars:
    px, w, h = mod.ft_render_mono(face, ch, px_size=16)
    canvas16 = mod.blit_center(px, w, h, 16, 16)
    g8x16 = mod.compress_16w_to_8w(canvas16, mode="or")
    out += mod.glyph8x16_to_gba4bpp(g8x16)
  return bytes(out)


def inject_fonts(
    rom_path: str | Path,
    chars: list[str],
    font_path_8x8: str | Path,
    font_path_8x16: str | Path,
) -> dict[str, dict[str, Any]]:
  """
  根据计算出的位置向 ROM 注入 8x8/8x16 字模及 mapping，并返回字符→位置信息的 dict 供后续 ROM 文本使用。
  - 先按 chars 顺序计算每字的 mapping_key、8x8/8x16 font_entry 等；
  - 用 font_path_8x8 / font_path_8x16 渲染出字模，从 8x8font_entry / 8x16font_entry 注入；
  - 从 ENTRY_MAPPING_8x8 / ENTRY_MAPPING_8x16 注入 [u16 key, u16 val] 小端序；
  - 返回 { char: { 'mapping_key', '8x16', '8x8', '8x8font_entry', '8x16font_entry' } }。
  """
  n = len(chars)
  # 1) 计算位置 dict（与原先 compute_mapping_offset 一致）
  mapping: dict[str, dict[str, Any]] = {}
  for i, char in enumerate(chars):
    mapping[char] = {
      "mapping_key": LAST_MAPPING_OFFSET_8x16 + i,
      "8x16": LAST_FONT_OFFSET_8x16 + i,
      "8x8": LAST_FONT_OFFSET_8x8 + i,
      "8x8font_entry": ENTRY_FONT_8x8 + (i * BYTES_PER_CHAR_8x8),
      "8x16font_entry": ENTRY_FONT_8x16 + (i * BYTES_PER_CHAR_8x16),
    }

  # 2) 用 8x8/8x16 字体渲染字模
  data_8x8 = _render_8x8(chars, font_path_8x8)
  data_8x16 = _render_8x16(chars, font_path_8x16)

  rom_path = Path(rom_path)
  with open(rom_path, "r+b") as f:
    # 3) 注入 8x8 字模：从 8x8font_entry 起每字 0x20 字节
    for i in range(n):
      off = ENTRY_FONT_8x8 + i * BYTES_PER_CHAR_8x8
      f.seek(off)
      f.write(data_8x8[i * BYTES_PER_CHAR_8x8 : (i + 1) * BYTES_PER_CHAR_8x8])

    # 4) 注入 8x16 字模：从 8x16font_entry 起每字 0x40 字节
    for i in range(n):
      off = ENTRY_FONT_8x16 + i * BYTES_PER_CHAR_8x16
      f.seek(off)
      f.write(data_8x16[i * BYTES_PER_CHAR_8x16 : (i + 1) * BYTES_PER_CHAR_8x16])

    # 5) 注入 mapping：key = mapping_key（小端 u16），val 分别为 8x16/8x8 的 font offset
    for i in range(n):
      mapping_key = LAST_MAPPING_OFFSET_8x16 + i
      val_8x16 = LAST_FONT_OFFSET_8x16 + i
      val_8x8 = LAST_FONT_OFFSET_8x8 + i

      f.seek(ENTRY_MAPPING_8x16 + i * 4)
      f.write(struct.pack("<HH", mapping_key & 0xFFFF, val_8x16 & 0xFFFF))
      f.seek(ENTRY_MAPPING_8x8 + i * 4)
      f.write(struct.pack("<HH", mapping_key & 0xFFFF, val_8x8 & 0xFFFF))

    # 6) 写入 8x8/8x16 字符数：LAST_*_COUNT + 写入字符数，u32 小端序
    f.seek(ENTRY_8x8_COUNT)
    f.write(struct.pack("<I", (LAST_8x8_COUNT + n) & 0xFFFFFFFF))
    f.seek(ENTRY_8x16_COUNT)
    f.write(struct.pack("<I", (LAST_8x16_COUNT + n) & 0xFFFFFFFF))

  return mapping

def load_translations():
  with open(TRANSLATIONS_FILE_PATH, 'rb') as f:
    data = json.load(f)
  return data


def apply_prepatch(rom_path: str | Path, prepatch_path: str | Path | None = None) -> int:
  """
  从 prepatch.json 读取差异列表（与 differ.py 输出格式一致：pos + bytes），
  按顺序写入 ROM 对应位置。若 prepatch_path 未指定则使用默认 PREPATCH_FILE_PATH。
  返回写入的 patch 条数；若文件不存在则返回 0。
  """
  path = Path(prepatch_path or PREPATCH_FILE_PATH)
  if not path.exists():
    return 0
  with open(path, "r", encoding="utf-8") as f:
    patches = json.load(f)
  if not patches:
    return 0
  rom_path = Path(rom_path)
  with open(rom_path, "r+b") as f:
    for item in patches:
      pos = item["pos"]
      offset = int(pos, 16) if isinstance(pos, str) else int(pos)
      raw = item["bytes"]
      data = bytes(b & 0xFF for b in raw)
      f.seek(offset)
      f.write(data)
  return len(patches)

def take_chars(data: list[dict]):
  fonts = set()
  for translation in data:
    if translation["skiped"]:
      continue
    if translation["translation"] == "":
      continue
    chars = translation['translation']
    for char in chars:
      if not char.isprintable():
        continue
      fonts.add(char)
  return sorted(fonts)

# 全角空格，用于与原文长度对齐时填充
FULL_WIDTH_SPACE = "　"

# 空格（半角/全角）写入 ROM 时使用 Shift-JIS 编码 0x8140（全角空格）
SPACE_ROM_BYTES = bytes([0x81, 0x40])


def _parse_offset(offset: str | int) -> int:
  """将 translations.json 中的 offset 转为整数（支持 0x 十六进制字符串）。"""
  if isinstance(offset, int):
    return offset
  s = offset.strip()
  if s.startswith("0x") or s.startswith("0X"):
    return int(s, 16)
  return int(s, 10)


def _encode_char_for_rom(ch: str, mapping: dict[str, dict[str, Any]]) -> bytes:
  """将单个字符编码为 ROM 用 2 字节：空格用 0x8140，其他用 mapping_key 大端序；未在 mapping 中的字符用 Shift-JIS。"""
  if ch in (" ", FULL_WIDTH_SPACE):
    return SPACE_ROM_BYTES
  if ch in mapping:
    key = mapping[ch]["mapping_key"] & 0xFFFF
    return struct.pack(">H", key)
  # 未在 mapping 中的字符（如未翻译的日文）用 Shift-JIS
  return ch.encode("shift_jis", errors="replace")[:2].ljust(2, b"\x00")


def encode_translation_for_rom(text: str, mapping: dict[str, dict[str, Any]]) -> bytes:
  """将整段译文编码为 ROM 用字节：每字 2 字节，空格 0x8140，其余为 mapping_key 大端序（或 Shift-JIS）。"""
  out = bytearray()
  for ch in text:
    out += _encode_char_for_rom(ch, mapping)
  return bytes(out)


def patch_translations_to_rom(
    rom_path: str | Path,
    data: list[dict],
    mapping: dict[str, dict[str, Any]],
) -> None:
  """根据 translations.json 的 offset，用 mapping 将译文编码后写入 ROM 对应位置。"""
  rom_path = Path(rom_path)
  with open(rom_path, "r+b") as f:
    for entry in data:
      if entry.get("skiped"):
        continue
      trans = entry.get("translation", "")
      if not trans:
        continue
      orig = entry.get("original", "")
      s = translation_to_fixed_length(trans, orig)
      offset = _parse_offset(entry["offset"])
      encoded = encode_translation_for_rom(s, mapping)
      f.seek(offset)
      f.write(encoded)


def translation_to_fixed_length(translation: str, original: str) -> str:
  """将译文按原文长度对齐：不足用全角空格右填充，过长截断。用于写入 ROM 等固定长度场景。"""
  orig_len = len(original)
  s = (translation or "").strip()
  if len(s) >= orig_len:
    return s[:orig_len]
  # 与 translate_with_glm.align_length 一致：原文尾有全角空格则用全角填充
  pad_char = FULL_WIDTH_SPACE if (original.endswith(FULL_WIDTH_SPACE) or FULL_WIDTH_SPACE in original[-10:]) else " "
  return s + pad_char * (orig_len - len(s))


def validate_translations(data: list[dict]):
  """校验：译文长度不得超过原文（可更短，写入时由 translation_to_fixed_length 填充）。"""
  for translation in data:
    if translation["skiped"]:
      continue
    if translation["translation"] == "":
      continue
    orig = translation["original"]
    trans = translation["translation"]
    if len(trans) > len(orig):
      raise ValueError(
        f"translation length ({len(trans)}) must not exceed original length ({len(orig)}), offset: {translation['offset']}"
      )



@click.command(help="校验译文并向 ROM 注入扩展字模与映射，返回字符位置 dict 供后续文本用")
@click.argument("rom_path", type=click.Path(exists=True, path_type=Path))
@click.argument("font_8x8", type=click.Path(exists=True, path_type=Path))
@click.argument("font_8x16", type=click.Path(exists=True, path_type=Path), required=False)
@click.option("--out-rom", "-o", type=click.Path(path_type=Path), help="输出到此 ROM 文件，不修改原 ROM")
@click.option("--out-mapping", "-m", type=click.Path(path_type=Path), help="将返回的字符→位置 dict 写入此 JSON 文件，供后续 ROM 文本使用")
def main(rom_path: Path, font_8x8: Path, font_8x16: Path | None, out_rom: Path | None, out_mapping: Path | None) -> None:
  """
  校验译文并向 ROM 注入扩展字模与映射，返回字符位置 dict 供后续文本用。

  Args:
    rom_path: GBA ROM 文件路径。
    font_8x8: 8x8 字体文件路径（如 TTF），用于渲染小字。
    font_8x16: 可选。8x16 字体文件路径；不传则与 8x8 使用同一字体。
    out_rom: 可选。指定则输出到此 ROM 文件，不修改原 ROM。
    out_mapping: 可选。将字符→位置 dict 写入的 JSON 路径，供后续 ROM 文本使用。

  Example:
    python patch.py rom.gba font.ttf -o patched.gba -m font_mapping.json
    python patch.py rom.gba debug/fusion-pixel-8px-monospaced-zh_hans.ttf debug/SourceHanSans-VF.ttf -o patched.gba  -m font_mapping.json
    python patch.py rom.gba debug/MZPXorig.ttf debug/fusion-pixel-12px-monospaced-zh_hans.ttf -o patched.gba  -m font_mapping.json
  """
  font_16 = font_8x16 if font_8x16 is not None else font_8x8
  if font_8x16 is None:
    click.echo("未指定 8x16 字体，8x8 与 8x16 使用同一字体")

  data = load_translations()
  validate_translations(data)
  chars = take_chars(data)
  click.echo(f"chars count: {len(chars)}")

  target_rom = out_rom if out_rom else rom_path
  if out_rom:
    shutil.copy2(rom_path, out_rom)
    click.echo(f"已复制 {rom_path} -> {out_rom}")

  n_prepatch = apply_prepatch(target_rom)
  if n_prepatch:
    click.echo(f"已从 prepatch.json 应用 {n_prepatch} 处 prepatch 到 {target_rom}")

  mapping = inject_fonts(target_rom, chars, font_8x8, font_16)
  click.echo(f"已向 {target_rom} 注入 {len(chars)} 字 8x8/8x16 字模与映射表")

  patch_translations_to_rom(target_rom, data, mapping)
  click.echo("已根据 translations.json 的 offset 与 mapping 替换 ROM 内对应文本")

  if out_mapping:
    with open(out_mapping, "w", encoding="utf-8") as f:
      json.dump(mapping, f, ensure_ascii=False, indent=2)
    click.echo(f"字符位置 dict 已写入 {out_mapping}")


if __name__ == "__main__":
  main()