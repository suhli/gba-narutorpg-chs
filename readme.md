# 火影忍者 RPG 汉化工程 (GBA)

本仓库为 GBA 游戏《火影忍者 RPG》的汉化与发布工程，**不包含、不分发任何 ROM 文件**。发布形式为：**汉化数据 + 与原版 ROM 的 binary diff**，配合 **HTML 网页 Patcher**，由用户在本机使用自有原版 ROM 打补丁得到汉化版。本工程采用 **MIT License** 开源，详见 [LICENSE](LICENSE)。

## 发布与使用方式

- **不提供 ROM**：请自行准备原版《火影忍者 RPG》GBA ROM。
- **补丁方式**：提供与**原版 ROM** 的 **binary diff**（补丁文件）以及 **HTML Patcher** 源码/页面。
- **用户流程**：在 [Patcher 页面](https://suhli.github.io/gba-narutorpg-chs/) 选择本地原版 ROM → 应用补丁 → 下载生成的汉化 ROM。

## 工程结构

```
gba-narutorpg-chs/
├── readme.md              # 本文件
├── LICENSE                # MIT License
├── hexproj/               # 静态分析：ImHex 工程
│   ├── font_edit.hexproj  # 字体/映射等标注（需自备 ROM 并重命名为 font_edit）
│   └── original.hexproj   # 原版 ROM 分析用工程（可选）
├── python/                # Python 工具脚本
│   ├── requirements.txt   # freetype-py, pillow, click
│   ├── patch.py           # 构建汉化 ROM：字模注入 + 译文写回（产出供 differ 生成 diff）
│   ├── differ.py          # 生成原版→汉化 ROM 的 diff.json（供网页 Patcher 使用）
│   └── debug/             # 字模、文本导出等脚本
│       ├── 8x8_font.py    # TTF → 8×8 GBA 字模
│       ├── 8x16_font.py   # TTF → 8×16 GBA 字模
│       ├── text_dumper.py # ROM 文本导出为 JSON（Shift-JIS）
│       └── text_dump/     # 文本导出输出（text_chunk_*.json）
└── patcher/               # HTML Patcher 源码
    └── diff.json          # 汉化补丁（由 python/differ.py 生成）
```

| 模块 | 说明 | 状态 |
|------|------|------|
| **hexproj** | ImHex 工程：ROM 内字体、mapping、二分查找等区域标注，便于分析与手工编辑 | ✅ 已有 |
| **python** | 构建汉化 ROM（patch.py）与生成 diff.json（differ.py）的流水线；字模/文本导出脚本 | ✅ 就绪 |
| **patcher** | 网页端 Patcher：用户在本机用 **diff.json** 对原版 ROM 打补丁得到汉化 ROM（含 ROM 内预制 patch）；在线地址见下方 | ✅ 可用 |

---

## 开发方式

### 环境与依赖

- **Python**：3.14+，用于汉化构建与 diff 生成（见下方 python 模块）。
- **Node/pnpm**：用于 Patcher 前端开发与构建（见下方 patcher 模块）。
- **ImHex**（可选）：用于 ROM 静态分析与字体编辑（见下方 hexproj 模块）。

### hexproj（ImHex 静态分析）

- 使用 [ImHex](https://github.com/WerWolv/ImHex) 打开工程，需在同目录下放置并重命名好的 GBA ROM。

| 工程文件 | 用途 | 所需 ROM 文件名 |
|----------|------|-----------------|
| **font_edit.hexproj** | 字体编辑：字模、mapping、二分查找等标注 | 将 ROM 重命名为 `font_edit`（或 `font_edit.gba`） |
| **original.hexproj** | 原版 ROM 静态分析、阅读与定位 | 将原版 ROM 重命名为 **`original.gba`** |

**font_edit 使用**：ROM 放到 `hexproj/`，重命名为 `font_edit` 或 `font_edit.gba`，用 ImHex 打开 `font_edit.hexproj`。  
**original 使用**：原版 ROM 重命名为 `original.gba`，用 ImHex 打开 `original.hexproj`。

工程内已标注：8×8/8×16 字模与 mapping、迁移后二分查找、新加 8×8 mapping、8×16 映射引用、菜单表与剧情样本等，便于汉化时定位与修改。请使用与本工程对应的 GBA ROM，否则偏移可能不匹配；ROM 需自行准备，仓库不包含任何 ROM。

### python（汉化构建与 diff 生成）

- **用途**：制作汉化数据与 diff，**不是**用户打补丁用。`patch.py` 在本地将字模与译文写回 ROM，产出完整汉化 ROM；`differ.py` 比较原版与汉化 ROM，生成 **diff.json** 供网页 Patcher 使用。字模使用**思源黑体**（Source Han Sans）渲染。

**依赖**：

```bash
pip install -r python/requirements.txt   # freetype-py, pillow, click
```

**常用命令**（在仓库根目录执行）：

| 操作 | 命令 |
|------|------|
| 构建汉化 ROM | `python python/patch.py 原版.gba 思源黑体.ttf 思源黑体.ttf -o 汉化.gba -m font_mapping.json`（需已存在 `translate/translations.json`） |
| 生成 diff.json | `python python/differ.py 原版.gba 汉化.gba -o patcher/diff.json` |
| 8×8 字模（debug） | `python python/debug/8x8_font.py`（脚本内配置 `font_path`、`chars`） |
| 8×16 字模（debug） | `python python/debug/8x16_font.py` |
| 文本导出（debug） | `python python/debug/text_dumper.py`（脚本内配置 `ROM_PATH`；输出到 `python/debug/text_dump`） |

字模输出为 `.bin` 与 `_preview.png`；文本导出为 `text_dump/text_chunk_*.json`。

### patcher（网页 Patcher）

- **技术栈**：Vite + Vue 3 + TypeScript，UnoCSS，包管理器 **pnpm**。
- **diff.json**：汉化补丁，由 `python/differ.py` 生成后放入 `patcher/diff.json`，格式为 `[{"pos": "0x...", "bytes": [...]}]`。

**开发与构建**：

```bash
cd patcher
pnpm install
pnpm dev      # 开发
pnpm build    # 构建，产物输出到 workspace/pages（供 GitHub Pages 托管）
pnpm preview  # 预览构建结果
```

用户打开部署页面或本地 `pnpm preview`，选择原版 GBA ROM，点击「打补丁并下载」即可；ROM 不上传，全部在浏览器内完成。

---

## 各模块说明

### hexproj（静态分析）

- 使用 [ImHex](https://github.com/WerWolv/ImHex) 打开 `font_edit.hexproj`，需在同目录下放置并重命名为 `font_edit` 的 GBA ROM。
- 工程内已标注 8×8/8×16 字模、mapping、二分查找函数、菜单与剧情样本等（详见上文「开发方式 → hexproj」）。

### python（脚本工具）

- **patch.py**：校验 `translate/translations.json`，从 TTF 渲染 8×8/8×16 字模并注入 ROM，写入扩展字符映射，再将汉化文本写回 ROM，产出完整汉化 ROM，供 differ 生成 diff。
- **differ.py**：比较原版 ROM 与汉化 ROM，生成 diff.json，供 Patcher 网页使用。用户实际打补丁请使用 Patcher 页面。
- **debug/**：8×8/8×16 字模脚本、`text_dumper.py` 文本导出（Shift-JIS 扫描，导出为 JSON 分块）。依赖见 `requirements.txt`。

### patcher（HTML Patcher）

- **在线 Patcher**：[https://suhli.github.io/gba-narutorpg-chs/](https://suhli.github.io/gba-narutorpg-chs/)
- 用户在本机选择原版 ROM，网页加载 **diff.json** 对其打补丁，在浏览器内生成汉化 ROM 并下载。补丁内容包含 ROM 内预制修改与字模/译文等汉化数据。
- 纯前端 HTML/JS，无后端、无上传 ROM，所有处理在用户本机完成。

## License

本工程采用 [MIT License](LICENSE) 开源。

## 法律与免责

- 本工程仅提供汉化数据与打补丁工具，不提供任何游戏 ROM。
- 请仅对您合法拥有的原版 ROM 进行打补丁；使用与传播 ROM 的责任由用户自行承担。
