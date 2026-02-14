# HTML Patcher [WIP]

本目录为**网页端 Patcher** 的源码：用户在本机选择原版 GBA ROM，在浏览器中应用预置的 binary diff，生成汉化 ROM 并下载。**不上传 ROM，无后端**。

## 目录与补丁数据

- **`diff.json`**：汉化补丁的**变更内容**。格式为 JSON 数组，每项为 `{"pos": "0x...", "bytes": [u8, ...]}`，表示在原版 ROM 的 `pos` 处写入 `bytes`。由 [python/differ.py](../python/differ.py) 比较「原版 ROM」与「汉化 ROM」生成，生成后放入本目录即可供 Patcher 使用。
- **readme.md**：本说明。

## 计划功能

- 纯前端（HTML + JavaScript）：选择本地原版《火影忍者 RPG》ROM 文件
- 加载本目录的 `diff.json`（汉化补丁）
- 在浏览器内按 `pos`/`bytes` 写回原版 ROM，完成打补丁，并触发汉化 ROM 的下载

## 当前状态

🚧 **进行中**：补丁数据 `diff.json` 已就绪；Patcher 页面与打补丁逻辑待实现。

## 使用方式

（待 Patcher 实现后补充：如何打开页面、支持的文件名/校验方式等。）
