---
date: 2026-06-25
tags:
  - claude-code
  - skill
  - agent-reach
  - 工具安装
---

## 背景

给 Claude Code 安装 Agent Reach，让 AI Agent 能直接搜索 Twitter/X、Reddit、YouTube、B站、小红书、V2EX、RSS 等 13 个平台，零 API 费用。

## 安装过程

### 1. 安装 Skill

```bash
npx skills add Panniantong/Agent-Reach@agent-reach -g -y
```

安装到 `~\.agents\skills\agent-reach\`，全局可用。

### 2. 安装 CLI 工具

```bash
pip install https://github.com/Panniantong/agent-reach/archive/main.zip
```

版本: `agent-reach 1.5.0`，连带安装 `feedparser`、`loguru`、`yt-dlp`。

### 3. 初始化环境

```bash
agent-reach install --env=auto
```

自动检测并安装 Node.js、yt-dlp 等系统依赖，初始化 mcporter 搜索后端。

### 4. 全渠道安装

```bash
agent-reach install --channels=all
```

补充安装各平台 CLI 后端:
- `bilibili-cli` (B站) — pip 安装
- `twitter-cli` (Twitter/X) — pip 安装
- `mcporter` (搜索后端) — npm 全局安装

### 5. OpenCLI Chrome 扩展

从 GitHub Releases 下载 `opencli-extension-v1.0.20.zip`，解压到 `D:\Agent\opencli-extension\`，Chrome 开发者模式加载。

> [!note] 关键点
> Chrome 商店版扩展不兼容，必须用 GitHub 解包版手动加载。加载后在 `opencli doctor` 中选择默认 profile (`opencli profile use <name>`)。

### 6. 更新 CLAUDE.md

在 `~\.claude\CLAUDE.md` 全局 Skills 列表中补上 `agent-reach` 条目，路径修正为 `~/.agents/skills/`。

## 最终状态

**8/13 渠道可用:**

| 状态 | 渠道 | 后端 |
|------|------|------|
| ✅ | YouTube | yt-dlp |
| ✅ | V2EX | 公开 API |
| ✅ | RSS/Atom | feedparser |
| ✅ | 任意网页 | Jina Reader |
| ✅ | Twitter/X | OpenCLI |
| ✅ | Reddit | OpenCLI |
| ✅ | B站 | bili-cli |
| ✅ | 小红书 | OpenCLI |

**未安装 (不需要):**
- GitHub (gh CLI 需管理员权限)
- Exa 语义搜索 (需 API key)
- 小宇宙/雪球/LinkedIn (暂不需要)
