# fashion16_to_gba8x16.py
# pip install freetype-py pillow
import freetype
from PIL import Image

INK, BG = 3, 0x11

def ft_render_mono(face, ch, px_size=16):
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
    out = [[0]*8 for _ in range(16)]
    for y in range(16):
        for x in range(8):
            a = src16x16[y][2*x]
            b = src16x16[y][2*x+1]
            if mode == "and":
                out[y][x] = 1 if (a and b) else 0
            else:  # "or" / "major"
                out[y][x] = 1 if (a or b) else 0
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

def main():
    # 改成你下载的 FashionBitmap16 字体文件名
    font_path = "FashionBitmap16_0.092.ttf"

    # 要导出的字符
    chars = "这里是"
    out_prefix = "fb16_8x16"

    face = freetype.Face(font_path)

    out_bin = bytearray()
    glyphs01 = []

    for ch in chars:
        px, w, h = ft_render_mono(face, ch, px_size=16)
        canvas16 = blit_center(px, w, h, 16, 16)          # 贴到 16x16
        g8x16 = compress_16w_to_8w(canvas16, mode="or")   # 16->8 压缩
        glyphs01.append(g8x16)

        out_bin += glyph8x16_to_gba4bpp(g8x16, INK, BG)   # 64 bytes/char

    with open(out_prefix + ".bin", "wb") as f:
        f.write(out_bin)

    make_preview_8x16(glyphs01).save(out_prefix + "_preview.png")
    print("Preview:", out_prefix + "_preview.png")
    print("BIN:", out_prefix + ".bin", f"({len(out_bin)} bytes)")

    # 每个字 dump 一下 64 bytes
    offset = 0
    for ch in chars:
        chunk = out_bin[offset:offset+64]
        offset += 64
        print(f"CHAR '{ch}' U+{ord(ch):04X} (64 bytes)")
        print(hex_dump(chunk))
        print()

if __name__ == "__main__":
    main()
