# Python 工具脚本

本目录包含与《火影忍者 RPG》汉化相关的 Python 脚本，与仓库其他模块配合使用。

## 目录结构

```
python/
├── readme.md
├── requirements.txt    # 依赖：freetype-py, pillow, click
├── patch.py            # 构建汉化 ROM：校验译文、注入字模与映射、汉化文本写回（产出供 differ 用）
├── differ.py           # 生成原版→汉化 ROM 的 diff.json，供网页 Patcher 使用
└── debug/              # 字模与文本导出脚本
    ├── 8x8_font.py     # TTF → 8×8 字模，输出 GBA 4bpp .bin + 预览图
    ├── 8x16_font.py    # TTF → 8×16 字模（16×16 压成 8×16），输出 .bin + 预览图
    ├── text_dumper.py  # 从 ROM 按 Shift-JIS 扫描文本，导出为 JSON 分块
    ├── charsets.binary # 可选：二进制码表 [u16 key][u16 value]，用于过滤导出字符
    └── text_dump/      # text_dumper 输出目录（text_chunk_001.json …）
```

## 已实现功能

### 构建汉化 ROM（patch.py）

- **patch.py**：在本地校验 `translate/translations.json`，从 TTF 渲染 8×8/8×16 字模并注入 ROM，写入扩展字符映射，再将汉化文本写回 ROM，产出**完整汉化 ROM**。该 ROM 仅供后续用 differ 生成 diff；**用户打补丁请使用网页 Patcher + diff.json**（且 ROM 内还有预制 patch，以 diff 形式统一应用）。

### 生成 diff（differ.py）

- **differ.py**：比较原版 ROM 与汉化 ROM，生成 diff（`pos` + `bytes` 数组），输出为 **diff.json**，供 [patcher](../patcher/) 网页使用。用户通过 Patcher 页面选择原版 ROM、应用此 diff 得到汉化 ROM。

### 字模（debug 脚本）

- **8×8 字模**（`debug/8x8_font.py`）：使用 FreeType MONO 渲染 TTF 为 8×8 像素，转为 GBA 4bpp tile，输出 `.bin` 及 `_preview.png`。
- **8×16 字模**（`debug/8x16_font.py`）：渲染 16×16 后按列压缩为 8×16，转为 GBA 4bpp（每字 64 字节），输出 `.bin` 及预览图。

**字体**：当前 8×8 与 8×16 字模均使用**思源黑体**（Source Han Sans，如 `SourceHanSansSC-VF.ttf`）渲染。上述脚本为实验用途，字体路径、字符列表需在脚本内修改。

### 文本导出（debug 脚本）

- **文本导出**（`debug/text_dumper.py`）：从 ROM 指定偏移（默认 `0x6DA84`）起按 Shift-JIS 扫描，提取剧情/菜单等日文文本，按长度与聚类分块导出为 `text_dump/text_chunk_*.json`。可选用 `charsets.binary` 码表过滤合法字符。脚本内需配置 `ROM_PATH`、`OUTPUT_DIR` 等。

## 依赖与运行

- **Python** 3.14+。
- **依赖**：`pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn` 并 `pip install -r requirements.txt`（当前为 `freetype-py`、`pillow`、`click`；`differ.py` 仅需 `click`）。
- **运行示例**（在仓库根目录或 `python` 目录下）：
  - **构建汉化 ROM**：`python python/patch.py 原版.gba 思源黑体.ttf 思源黑体.ttf -o 汉化.gba -m font_mapping.json`（两个 TTF 分别为 8×8、8×16 用，可同一文件；需已存在 `translate/translations.json`）。产出汉化.gba 后，用下一行生成 diff。
  - **生成 diff.json**：`python python/differ.py 原版.gba 汉化.gba -o patcher/diff.json`，将 diff 写入 [patcher](../patcher/) 的 `diff.json`，供网页 Patcher 使用。
  - 8×8：`python python/debug/8x8_font.py`（需在脚本中配置 `font_path`、`chars` 等）。
  - 8×16：`python python/debug/8x16_font.py`（同上，与 8×8 一样可使用思源黑体 TTF）。
  - 文本导出：`python python/debug/text_dumper.py`（需在脚本中配置 `ROM_PATH` 为原版 ROM 路径；输出到 `OUTPUT_DIR`，默认 `python/debug/text_dump`）。

字模输出为同目录或脚本内 `out_prefix` 指定的 `.bin` 与 `_preview.png`；文本导出为 `text_dump/text_chunk_*.json`。
