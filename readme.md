# 火影忍者 RPG 汉化工程 (GBA)

本仓库为 GBA 游戏《火影忍者 RPG》的汉化与发布工程，**不包含、不分发任何 ROM 文件**。发布形式为：**汉化数据 + 与原版 ROM 的 binary diff**，配合 **HTML 网页 Patcher**，由用户在本机使用自有原版 ROM 打补丁得到汉化版。

## 发布与使用方式

- **不提供 ROM**：请自行准备原版《火影忍者 RPG》GBA ROM。
- **补丁方式**：提供与**原版 ROM** 的 **binary diff**（补丁文件）以及 **HTML Patcher** 源码/页面。
- **用户流程**：在 Patcher 页面选择本地原版 ROM → 应用补丁 → 下载生成的汉化 ROM。

## 工程结构

```
gba-narutorpg-chs/
├── readme.md              # 本文件
├── hexproj/               # 静态分析：ImHex 工程
│   ├── font_edit.hexproj  # 字体/映射等标注（需自备 ROM 并重命名为 font_edit）
│   └── readme.md
├── python/                # Python 工具脚本 [WIP]
│   └── readme.md
└── patcher/               # HTML Patcher 源码 [WIP]
    └── readme.md
```

| 模块 | 说明 | 状态 |
|------|------|------|
| **hexproj** | ImHex 工程：ROM 内字体、mapping、二分查找等区域标注，便于分析与手工编辑 | ✅ 已有 |
| **python** | 从 TTF 提取字模、导出 ROM 内文本、生成/校验 binary diff 等脚本 | 🚧 WIP |
| **patcher** | 网页端 Patcher：加载用户 ROM + 应用 diff，输出汉化 ROM | 🚧 WIP |

## 各模块说明

### hexproj（静态分析）

- 使用 [ImHex](https://github.com/WerWolv/ImHex) 打开 `font_edit.hexproj`，需在同目录下放置并重命名为 `font_edit` 的 GBA ROM。
- 工程内已标注 8×8/8×16 字模、mapping、二分查找函数、菜单与剧情样本等，详见 [hexproj/readme.md](hexproj/readme.md)。

### python（脚本工具）[WIP]

计划包含：

- 从 TTF 提取字模并转换为游戏所用格式
- 从 ROM 导出/导入文本
- 生成或校验与原版 ROM 的 binary diff（供 Patcher 使用）

### patcher（HTML Patcher）[WIP]

计划包含：

- 纯前端 HTML/JS：选择本地原版 ROM 文件，应用预置的 binary diff，在浏览器内生成汉化 ROM 并触发下载。
- 无后端、无上传 ROM，所有处理在用户本机完成。

## 法律与免责

- 本工程仅提供汉化数据与打补丁工具，不提供任何游戏 ROM。
- 请仅对您合法拥有的原版 ROM 进行打补丁；使用与传播 ROM 的责任由用户自行承担。
