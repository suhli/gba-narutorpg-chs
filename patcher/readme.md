# HTML Patcher [WIP]

本目录为**网页端 Patcher** 的源码：用户在本机选择原版 GBA ROM，在浏览器中应用预置的 binary diff，生成汉化 ROM 并下载。**不上传 ROM，无后端**。

## 目录与补丁数据

- **`diff.json`**：汉化补丁的**变更内容**。格式为 JSON 数组，每项为 `{"pos": "0x...", "bytes": [u8, ...]}`，表示在原版 ROM 的 `pos` 处写入 `bytes`。由 [python/differ.py](../python/differ.py) 比较「原版 ROM」与「汉化 ROM」生成，生成后放入本目录即可供 Patcher 使用。
- **readme.md**：本说明。

## 技术栈

- **Vite** + **Vue 3** + **TypeScript**
- **UnoCSS**（原子化 CSS，图标使用 `@unocss/preset-icons` + `@iconify/json`）
- 包管理器：**pnpm**

## 功能

- 纯前端：选择本地原版《火影忍者 RPG》ROM 文件（.gba）
- 加载本目录的 `diff.json`（汉化补丁）
- 在浏览器内按 `pos`/`bytes` 写回原版 ROM，完成打补丁，并触发汉化 ROM 的下载

## 开发与构建

```bash
pnpm install
pnpm dev      # 开发
pnpm build    # 构建，产物输出到 workspace/pages（供 GitHub Pages 托管）
pnpm preview  # 预览构建结果
```

## 使用方式

打开部署后的页面（或本地 `pnpm preview`），选择原版 GBA ROM 文件，点击「打补丁并下载」即可。ROM 不会上传，全部在浏览器内完成。

