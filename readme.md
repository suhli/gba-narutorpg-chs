# 火影忍者 RPG 汉化工程 (GBA)

本仓库为 GBA 游戏《火影忍者 RPG》的汉化与发布工程，**不包含、不分发任何 ROM 文件**。发布形式为：**汉化数据 + 与原版 ROM 的 binary diff**，配合 **HTML 网页 Patcher**，由用户在本机使用自有原版 ROM 打补丁得到汉化版。

## 发布与使用方式

- **不提供 ROM**：请自行准备原版《火影忍者 RPG》GBA ROM。
- **补丁方式**：提供与**原版 ROM** 的 **binary diff**（补丁文件）以及 **HTML Patcher** 源码/页面。
- **用户流程**：在 [Patcher 页面](https://suhli.github.io/gba-narutorpg-chs/) 选择本地原版 ROM → 应用补丁 → 下载生成的汉化 ROM。

## 工程结构

```
gba-narutorpg-chs/
├── readme.md              # 本文件
├── hexproj/               # 静态分析：ImHex 工程
│   ├── font_edit.hexproj  # 字体/映射等标注（需自备 ROM 并重命名为 font_edit）
│   ├── original.hexproj   # 原版 ROM 分析用工程（可选）
│   └── readme.md
├── python/                # Python 工具脚本
│   ├── readme.md
│   ├── requirements.txt   # freetype-py, pillow, click
│   ├── patch.py           # 构建汉化 ROM：字模注入 + 译文写回（产出供 differ 生成 diff）
│   ├── differ.py          # 生成原版→汉化 ROM 的 diff.json（供网页 Patcher 使用）
│   └── debug/             # 字模、文本导出等脚本
│       ├── 8x8_font.py    # TTF → 8×8 GBA 字模
│       ├── 8x16_font.py   # TTF → 8×16 GBA 字模
│       ├── text_dumper.py # ROM 文本导出为 JSON（Shift-JIS）
│       └── text_dump/     # 文本导出输出（text_chunk_*.json）
└── patcher/               # HTML Patcher 源码
    └── readme.md
```

| 模块 | 说明 | 状态 |
|------|------|------|
| **hexproj** | ImHex 工程：ROM 内字体、mapping、二分查找等区域标注，便于分析与手工编辑 | ✅ 已有 |
| **python** | 构建汉化 ROM（patch.py）与生成 diff.json（differ.py）的流水线；字模/文本导出脚本 | ✅ 就绪 |
| **patcher** | 网页端 Patcher：用户在本机用 **diff.json** 对原版 ROM 打补丁得到汉化 ROM（含 ROM 内预制 patch）；在线地址见下方 | ✅ 可用 |

## 各模块说明

### hexproj（静态分析）

- 使用 [ImHex](https://github.com/WerWolv/ImHex) 打开 `font_edit.hexproj`，需在同目录下放置并重命名为 `font_edit` 的 GBA ROM。
- 工程内已标注 8×8/8×16 字模、mapping、二分查找函数、菜单与剧情样本等，详见 [hexproj/readme.md](hexproj/readme.md)。

### python（脚本工具）

- **用途**：用于**制作**汉化数据与 diff，而非用户打补丁。`patch.py` 在本地将字模与译文写回 ROM，产出完整汉化 ROM；`differ.py` 比较原版与汉化 ROM，生成 **diff.json**。该 diff 供网页 Patcher 使用；用户实际打补丁请使用下方 Patcher 页面。另含 `debug/` 下 8×8/8×16 字模脚本、`text_dumper.py` 文本导出。**字模字体**：8×8 与 8×16 均使用**思源黑体**（Source Han Sans）渲染。依赖见 `requirements.txt`（freetype-py、pillow、click）。详见 [python/readme.md](python/readme.md)。

### patcher（HTML Patcher）

- **在线 Patcher**：[https://suhli.github.io/gba-narutorpg-chs/](https://suhli.github.io/gba-narutorpg-chs/)
- 用户在本机选择原版 ROM，网页加载 **diff.json** 对其打补丁，在浏览器内生成汉化 ROM 并下载。补丁内容包含 ROM 内预制修改与字模/译文等汉化数据。
- 纯前端 HTML/JS，无后端、无上传 ROM，所有处理在用户本机完成。

## 法律与免责

- 本工程仅提供汉化数据与打补丁工具，不提供任何游戏 ROM。
- 请仅对您合法拥有的原版 ROM 进行打补丁；使用与传播 ROM 的责任由用户自行承担。
