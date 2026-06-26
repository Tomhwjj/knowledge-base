---
date: 2026-06-24
tags: [claude-code, 配置, 项目整理]
---

## 做了什么

### Skill 安装与备份体系

- 安装 `frontend-design` skill（Anthropic 官方，34.8 万安装量，skills.sh #3）
- 建立完善的 **装 Skill 强制流程**：安装 → 同步 `.claude` → 备份 `vercel-skills` → commit + push
- 写入 CLAUDE.md 第 43-51 行，之后每次装 skill 必须逐条打勾确认

### GitHub CLI 部署

- 下载安装 `gh.exe` 到 `~/.local/bin/`
- 通过 token 完成认证（keyring 持久化存储，`repo` + `read:org` 权限）
- 给 `gh` 配好代理（写入 PowerShell profile）
- **教训**：之前 git push 能通是因为 git 配了代理，`gh` 需要单独配

### 配置备份体系

建立了 **Stop Hook 自动备份**，会话结束时自动触发：

| 备份仓库 | 源文件 | GitHub |
|----------|--------|--------|
| `claude-config-backup` | `~/.claude/CLAUDE.md` | Tomhwjj/claude-config-backup |
| `mcp-config-backup` | `~/.claude.json` | Tomhwjj/mcp-config-backup |

- 脚本：`~/.claude/scripts/backup-claude-config.ps1`
- Hook：`~/.claude/settings.json` → `Stop` 事件
- 原理：SHA256 哈希对比 → 有变化才 commit + push
- **与 memory/checklist 的区别**：hook 是程序级自动执行，不需要"记住"

### trading-system UI 重设计

- 应用 `frontend-design` skill 的设计原则
- 方向：**交易终端美学** — 数据优先、P&L 曲线 Hero、克制装饰
- 完整 Token 系统（12 个 CSS 变量）、等宽字体数据对齐、Chart.js 渐变填充
- 中国市场颜色惯例（红涨绿跌）

### 项目清理

- 删除 `mcp-backup`（混乱的历史遗留仓库）
- `.gitignore` 补漏：`claude-config-backup/`、`mcp-config-backup/`、`Git/`、`docs/`、`paper/`
- 新建项目铁律补充：**新建后必须回 `.gitignore` 加一行**

### vercel-skills 修复

- remote 从只读 `vercel-labs/skills.git` 切到 `Tomhwjj/skills-backup.git`
- 创建 GitHub 仓库 `skills-backup`，首版推了 `frontend-design` 源码

## 当前项目全景

`D:\Agent\git` 下 8 个项目：

| 项目 | 用途 |
|------|------|
| `paper-generator` | 论文工具链 |
| `image-recognition` | 图像识别 |
| `knowledge-base` | 本地知识库 |
| `OpenCLI` | CLI 参考 |
| `trading-system` | 选股+交易日志 |
| `vercel-skills` | skill 源码备份 |
| `claude-config-backup` | CLAUDE.md 版本历史 |
| `mcp-config-backup` | MCP 配置备份 |

## 已安装 Skills（12 个）

frontend-design、agent-reach、find-skills、skill-creator、image-recognition、paper-generator、humanize-chinese-academic、humanize-academic-writing、brainstorming、writing-plans、trading-system、knowledge-base、obsidian-skills、defuddle

## 关键教训

- **装 skill 必须走强制流程**，不能靠记忆
- **被纠正一次 → 写入 CLAUDE.md** 加固规则
- Hook 比 checklist 可靠，能用 hook 就别靠自觉
- 删东西前先看清楚里面有什么（mcp-backup 的教训）
