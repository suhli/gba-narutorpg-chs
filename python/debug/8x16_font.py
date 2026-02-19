# fashion16_to_gba8x16.py
# pip install freetype-py pillow click
import freetype
from pathlib import Path

import click
from PIL import Image

INK, BG = 3, 0x11

def ft_render_mono(face, ch, px_size=16, cell_size=None):
    """
    cell_size: 可选 (width, height)，如 (8, 12) 表示指定 8×12 格；不传则仅用 px_size 作为高度、宽度由字体比例决定。
    """
    if cell_size is not None:
        cw, ch_h = cell_size
        face.set_pixel_sizes(cw, ch_h)
    else:
        face.set_pixel_sizes(0, px_size)
    face.load_char(ch, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_MONO)
    bmp = face.glyph.bitmap
    w, h = bmp.width, bmp.rows
    buf = bmp.buffer
    pitch = bmp.pitch

    px = [[0]*w for _ in range(h)]
    for y in range(h):
        row = buf[y*pitch:(y+1)*pitch]
        for x in range(w):
            byte = row[x >> 3]
            bit = (byte >> (7 - (x & 7))) & 1
            px[y][x] = bit
    return px, w, h

def blit_center(src, sw, sh, dw, dh, xoff=0, yoff=0):
    dst = [[0]*dw for _ in range(dh)]
    ox = (dw - sw)//2 + xoff
    oy = (dh - sh)//2 + yoff
    for y in range(sh):
        ty = oy + y
        if 0 <= ty < dh:
            row = src[y]
            for x in range(sw):
                tx = ox + x
                if 0 <= tx < dw:
                    dst[ty][tx] = row[x]
    return dst

def compress_16w_to_8w(src16x16, mode="or"):
    """
    把 16x16 压成 8x16：每 2 列合并成 1 列
    mode:
      - "or"  : 2列任意有墨就算有（推荐，细线更不容易丢）
      - "and" : 2列都要有才算有（更细但容易断）
      - "major": 2列>=1 算有（等价 or，留个口子以后扩）
    """
    return compress_16w_to_8w_h(src16x16, height=16, mode=mode)


def compress_16w_to_8w_h(src_16wide, height, mode="or"):
    """把 16×height 压成 8×height：每 2 列合并成 1 列。"""
    out = [[0] * 8 for _ in range(height)]
    for y in range(height):
        for x in range(8):
            a = src_16wide[y][2 * x]
            b = src_16wide[y][2 * x + 1]
            if mode == "and":
                out[y][x] = 1 if (a and b) else 0
            else:
                out[y][x] = 1 if (a or b) else 0
    return out


def scale_8x12_to_8x16(grid_8x12):
    """将 8×12 点阵最近邻缩放到 8×16。"""
    out = [[0] * 8 for _ in range(16)]
    for y in range(16):
        sy = int(y * 12 / 16)
        if sy >= 12:
            sy = 11
        out[y] = grid_8x12[sy][:]
    return out


def pad_8x12_to_8x16(grid_8x12):
    """将 8×12 点阵垂直居中填充到 8×16（上下各 2 行空白）。"""
    out = [[0] * 8 for _ in range(16)]
    for y in range(12):
        out[y + 2][:] = grid_8x12[y]
    return out

def tile01_to_gba4bpp(tile01_8x8, ink=3, bg=BG):
    ink &= 0xF
    bg &= 0xF
    out = bytearray()
    for y in range(8):
        for x in range(0, 8, 2):
            p0 = ink if tile01_8x8[y][x] else bg
            p1 = ink if tile01_8x8[y][x+1] else bg
            out.append(((p1 & 0xF) << 4) | (p0 & 0xF))
    return bytes(out)

def glyph8x16_to_gba4bpp(g8x16, ink=3, bg=BG):
    top = [row[:] for row in g8x16[:8]]
    bot = [row[:] for row in g8x16[8:]]
    return tile01_to_gba4bpp(top, ink, bg) + tile01_to_gba4bpp(bot, ink, bg)

def make_preview_8x16(glyphs01, cols=32, scale=8):
    rows = (len(glyphs01) + cols - 1)//cols
    img = Image.new("L", (cols*8, rows*16), 0)
    for i, g in enumerate(glyphs01):
        tx, ty = (i % cols)*8, (i//cols)*16
        for y in range(16):
            for x in range(8):
                if g[y][x]:
                    img.putpixel((tx+x, ty+y), 255)
    return img.resize((img.width*scale, img.height*scale), Image.NEAREST)

def hex_dump(data: bytes):
    return " ".join(f"{b:02X}" for b in data)


@click.command(
    help="用 TrueType 字体将指定字符渲染为 8×16 点阵并导出 GBA 4bpp 图块与预览图。先按 8×12 渲染，再 pad 或 scale 到 8×16。",
    epilog="""
示例:
  python 8x16_font.py -f MZPXflat.ttf
  python 8x16_font.py -f MZPXflat.ttf --mode pad
  python 8x16_font.py -f MZPXflat.ttf --mode pad --chars "新游戏" -o out
  python 8x16_font.py -f MZPXflat.ttf --mode scale --scale 4
""",
)
@click.option("-f", "--font", "font_path", type=click.Path(exists=True, path_type=Path), default="MZPXflat.ttf", help="TTF 字体文件路径（默认 FashionBitmap16_0.092.ttf）")
@click.option("--chars", default="这里是", help="要导出的字符（默认「这里是」）")
@click.option("-o", "--output", "out_prefix", default="fb16_8x16", help="输出文件名前缀（.bin 与 _preview.png）（默认 fb16_8x16）")
@click.option("--mode", type=click.Choice(["pad", "scale"], case_sensitive=False), default="pad", help="8×12→8×16 方式: pad=上下留白居中, scale=按行缩放（默认 pad）")
@click.option("--scale", type=int, default=8, help="预览图放大倍数（默认 8）")
def main(font_path: Path, chars: str, out_prefix: str, mode: str, scale: int) -> None:
    face = freetype.Face(str(font_path.resolve()))
    to_8x16 = pad_8x12_to_8x16 if mode == "pad" else scale_8x12_to_8x16

    out_bin = bytearray()
    glyphs01 = []

    for ch in chars:
        px, w, h = ft_render_mono(face, ch, cell_size=(8, 12))
        canvas_8x12 = blit_center(px, w, h, 8, 12)
        g8x16 = to_8x16(canvas_8x12)
        glyphs01.append(g8x16)
        out_bin += glyph8x16_to_gba4bpp(g8x16, INK, BG)

    with open(out_prefix + ".bin", "wb") as f:
        f.write(out_bin)

    make_preview_8x16(glyphs01, scale=scale).save(out_prefix + "_preview.png")
    print("Preview:", out_prefix + "_preview.png")
    print("BIN:", out_prefix + ".bin", f"({len(out_bin)} bytes)")

    offset = 0
    for ch in chars:
        chunk = out_bin[offset : offset + 64]
        offset += 64
        print(f"CHAR '{ch}' U+{ord(ch):04X} (64 bytes)")
        print(hex_dump(chunk))
        print()


if __name__ == "__main__":
    main()
