# Python 工具脚本

本目录包含与《火影忍者 RPG》汉化相关的 Python 脚本，与仓库其他模块配合使用。

## 目录结构

```
python/
├── readme.md
├── requirements.txt    # 依赖：freetype-py, pillow
└── debug/             # 调试/实验用脚本
    ├── 8x8_font.py    # TTF → 8×8 字模，输出 GBA 4bpp .bin + 预览图
    └── 8x16_font.py   # TTF → 8×16 字模（16×16 压成 8×16），输出 .bin + 预览图
```

## 已实现功能

### 字模（debug 脚本）

- **8×8 字模**（`debug/8x8_font.py`）：使用 FreeType MONO 渲染 TTF 为 8×8 像素，转为 GBA 4bpp tile，输出 `.bin` 及 `_preview.png`。
- **8×16 字模**（`debug/8x16_font.py`）：渲染 16×16 后按列压缩为 8×16，转为 GBA 4bpp（每字 64 字节），输出 `.bin` 及预览图。

上述脚本为实验用途，字体路径、字符列表需在脚本内修改；后续会抽成可配置的 CLI 或工具库。

## 计划功能

- **字模**：封装为统一 CLI（指定 TTF、字符集、8×8/8×16），与 [hexproj](../hexproj/) 标注配合写回 ROM。
- **文本**：从 ROM 导出剧情/菜单等文本，或把汉化文本写回 ROM。
- **Binary diff**：生成「原版 ROM → 汉化 ROM」的 binary diff，供 [patcher](../patcher/) 使用；可选校验、合并等。

## 依赖与运行

- **Python** 3.14+。
- **依赖**：`pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn` 并 `pip install -r requirements.txt`（当前为 `freetype-py`、`pillow`）。
- **运行示例**（在 `python` 目录下）：
  - 8×8：`python debug/8x8_font.py`（需在脚本中配置 `font_path`、`chars` 等）。
  - 8×16：`python debug/8x16_font.py`（同上，需自备如 FashionBitmap16 等 TTF）。

输出为同目录或脚本内 `out_prefix` 指定的 `.bin` 与 `_preview.png`。
