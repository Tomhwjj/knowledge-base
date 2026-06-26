---
date: 2026-06-25
tags: [claude-code, mcp, playwright, chrome-devtools, 项目规范]
---

# Claude Code MCP 双件套整合 + 项目规范梳理

## MCP 整合

### 安装 Playwright MCP

- 包：`@playwright/mcp@0.0.76`
- 配置：`~/.claude.json` → `mcpServers.playwright`
- 参数：`--cdp-endpoint=chrome --caps=network,storage`
- **不复用 Chrome 已有登录态？装了 `--cdp-endpoint=chrome` 免除下载额外 Chromium（省 ~300MB）**

### 最终格局

| 服务器 | 定位 | 独有能力 |
|--------|------|----------|
| chrome-devtools | 日常浏览辅助 + 诊断 | Lighthouse、Heap、Performance、复用登录态 |
| playwright `--caps=network,storage` | 自动化补充 | 网络拦截 Mock、Cookie/Storage CRUD、`browser_run_code` 逃生舱 |

### 使用分工

- 日常浏览 / 填表单 / 看页面 → chrome-devtools
- Mock API / Cookie / Storage / 复杂自动化 → Playwright
- Lighthouse / 内存 / 性能 → chrome-devtools（Playwright 没有）
- 按需扩展 caps：`vision`（像素鼠标）、`testing`（测试断言）、`pdf`、`devtools`（视频）

## Skill vs MCP 分类（CLAUDE.md 重构）

之前的 CLAUDE.md 把 MCP 混在 Skills 列表里，现在拆清：

| 类型 | 本质 | 例子 |
|------|------|------|
| 纯提示词 Skill | 流程模板 / 工作流 | paper-generator, humanize-chinese-academic, trading-system |
| 带脚本的 Skill | 提示词 + 外部脚本 | image-recognition（Bash 调 Python 脚本） |
| MCP 工具 | 外部程序接口 / 原生函数调用 | chrome-devtools, playwright |

> 核心：Skill 教怎么用已有能力；MCP 给本来没有的能力。

## 项目规范完善

### 新建 vs 日常保存（拆清）

| 时机 | 做什么 | 频率 |
|------|--------|------|
| **新建项目** | `git init` → `commit -m "init"` → GitHub 建仓库 → `remote add` → `push` | 一次 |
| **日常保存** | `git add -A` → `commit -m "描述"` → `push` | 频繁 |

### .gitignore

`D:\Agent\git\.gitignore` 里列出所有子项目，防止子项目的 `.git` 被主仓库 track 成 gitlink。之前 `daily_stock_analysis`、`paper-generator`、`vercel-skills` 被嵌进去了，已清理。

## 概念澄清

- **origin** = 远程仓库 URL 的短别名
- **master** = 分支名，存在 `.git/refs/heads/master` 里，只是个 41 字节的指针文件
- **HEAD** = `.git/HEAD` 指向当前分支，决定你"在"哪个分支上
- **分支 ≠ 项目 ≠ 仓库**，每个 `.git` 文件夹有自己独立的 master

## 改动文件

- `~/.claude.json` — 新增 playwright MCP 配置
- `~/.claude/CLAUDE.md` — MCP 章节重写、Skill 分类、项目流程拆分
- `D:\Agent\git\.gitignore` — 子项目忽略列表
- `D:\Agent\git\mcp-backup\` — 配置文件备份
