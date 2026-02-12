# boutique7x7_to_gba8x8.py
# pip install freetype-py pillow
import freetype
from PIL import Image

INK, BG = 3, 0x11

def ft_render_mono(face, ch, px_size=8):
    face.set_pixel_sizes(0, px_size)
    face.load_char(ch, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_MONO)
    bmp = face.glyph.bitmap
    w, h = bmp.width, bmp.rows
    buf = bmp.buffer  # 1-bit packed, each row is pitch bytes
    pitch = bmp.pitch

    # 转成 0/1 像素
    px = [[0]*w for _ in range(h)]
    for y in range(h):
        row = buf[y*pitch:(y+1)*pitch]
        for x in range(w):
            byte = row[x >> 3]
            bit = (byte >> (7 - (x & 7))) & 1
            px[y][x] = bit
    return px, w, h

def blit_center(src, sw, sh, dw=8, dh=8, xoff=0, yoff=0):
    # 居中贴到 8x8，超出则裁切
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


def px_to_tile_8x8(px, w, h):
    """将渲染结果转为 8x8 tile：若已是 8x8 则直接用，否则居中贴到 8x8（会 pad）。"""
    if w == 8 and h == 8:
        return px
    return blit_center(px, w, h, 8, 8)

def tile01_to_gba4bpp(tile01, ink=3, bg=BG):
    # 强制保证在 0..15
    ink &= 0xF
    bg &= 0xF

    out = bytearray()
    for y in range(8):
        for x in range(0, 8, 2):
            b0 = 1 if tile01[y][x] else 0
            b1 = 1 if tile01[y][x+1] else 0
            p0 = ink if b0 else bg
            p1 = ink if b1 else bg
            out.append(((p1 & 0xF) << 4) | (p0 & 0xF))
    return bytes(out)

def make_preview(tiles01, cols=32, scale=8):
    rows = (len(tiles01) + cols - 1)//cols
    img = Image.new("L", (cols*8, rows*8), 0)
    for i, t in enumerate(tiles01):
        tx, ty = (i % cols)*8, (i//cols)*8
        for y in range(8):
            for x in range(8):
                if t[y][x]:
                    img.putpixel((tx+x, ty+y), 255)
    return img.resize((img.width*scale, img.height*scale), Image.NEAREST)
def hex_dump(data: bytes):
    return " ".join(f"{b:02X}" for b in data)

def main():
    font_path = "debug/fusion-pixel-8px-monospaced-zh_hans.ttf"
    chars = "新游戏"
    out_prefix = "debug/fusion-pixel-8px-monospaced-zh_hans"

    face = freetype.Face(font_path)

    tiles_bin = bytearray()
    tiles01 = []

    for ch in chars:
        px, w, h = ft_render_mono(face, ch, px_size=8)  # 关键：MONO 渲染
        tile = px_to_tile_8x8(px, w, h)                 # 8x8 直接用，否则居中 pad 到 8x8
        tiles01.append(tile)
        tiles_bin += tile01_to_gba4bpp(tile)

    with open(out_prefix + ".bin", "wb") as f:
        f.write(tiles_bin)

    make_preview(tiles01).save(out_prefix + "_preview.png")
    print("Preview:", out_prefix + "_preview.png")
    for ch in chars:
        px, w, h = ft_render_mono(face, ch, px_size=8)
        tile = px_to_tile_8x8(px, w, h)

        tile_bytes = tile01_to_gba4bpp(tile)

        print(f"CHAR '{ch}' U+{ord(ch):04X}")
        print(hex_dump(tile_bytes))
        print()


if __name__ == "__main__":
    main()
