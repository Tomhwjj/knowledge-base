---
date: 2026-06-22
tags:
  - claude-code
  - git
  - skill
  - 项目整理
---

# D:\Agent\git 仓库整理与 Skill 合并

## 1. 仓库目录整理

### 问题
`D:\Agent\git` 项目收纳目录混乱，存在旧版残留、命名模糊、缺少独立 git 仓库等问题。

### 操作

| 操作 | 说明 |
|------|------|
| 🗑️ 删 `paper-creator/` | 旧版 skill 副本，与 paper-generator 重叠 |
| ✏️ `paper-generator-project/` → `paper-generator` | 命名精简 |
| ✏️ `skills/` → `vercel-skills` | 标明是 vercel-labs 参考项目 |
| 🆕 `image-recognition/` git init | 从子文件夹 → 独立仓库 |
| 🆕 `knowledge-base/` git init | 从子文件夹 → 独立仓库 |
| 📝 更新 CLAUDE.md | 所有路径同步 |

### 整理后结构
```
D:\Agent\git/
├── Git/                  (Git 安装，保留)
├── paper/                (论文产出)
├── image-recognition/    → Tomhwjj/image-recognition
├── knowledge-base/       → Tomhwjj/knowledge-base
├── paper-generator/      → Tomhwjj/paper-generator
├── OpenCLI/              → jackwener/OpenCLI (参考)
└── vercel-skills/        → vercel-labs/skills (参考)
```

每个项目均有独立 `.git` + GitHub remote。

---

## 2. 确立项目保存规则

写入 [[../../c.%2C/Users/%E4%BD%95%E4%BC%9F/.claude/CLAUDE|CLAUDE.md]]：

### 两样东西，分开放

| 类型 | 位置 | 说明 |
|------|------|------|
| **安装好要用的** | `~/.claude/skills/` | Claude Code skill |
| **项目（备份/发布/分享）** | `D:\Agent\git/<项目名>/` | 独立仓库 |

### 铁律
- `D:\Agent\git` 里每个文件夹必须是独立 git 仓库（有 `.git` + GitHub remote）
- 不往里扔 skill 副本、安装程序、临时文件
- 命名一眼能看懂，旧版残留直接删

---

## 3. Skill 重新安装

`paper-creator/` 删除后，其中的 `paper-generator` 和 `humanize-chinese-academic` skill 失效。

从 `paper-generator` 项目源码重新安装：
- `npx skills add D:\Agent\git\paper-generator\paper-generator -g -y`
- `npx skills add D:\Agent\git\paper-generator\humanize-chinese-academic -g -y`

安装位置：`~\.agents\skills\` → symlink 到 Claude Code。

---

## 4. humanize-chinese-academic 策略合并

### 问题
中文版只有 6 轮 PaperPass 实测总结的 5 项**结构策略**（正则自动化），丢失了原版 `humanize-academic-writing` 的**语义策略**。

### 合并后的策略体系

#### 🐍 结构策略（Python 自动，zh_humanizer.py）
- 打破序号式平行结构
- 消除重复句式模板
- 自然过渡替代机械过渡
- 段落长度参差不齐
- 句式长短交错

#### 🧠 语义策略（Claude 手动，继承自原版）
- 减少抽象表达
- 增加学术声音与批判性
- 用具体性落地

#### 🔄 策略自进化
- `strategy_learner.py` + PaperPass 反馈 → 权重自调整

### 文件
- 源码：`D:\Agent\git\paper-generator\humanize-chinese-academic\SKILL.md`
- 安装：`~\.agents\skills\humanize-chinese-academic\SKILL.md`
- 提交：`ac45cb6`（已推 GitHub）

---

## 5. 其他发现

- Claude Code 聊天记录存于 `~/.claude/projects/`，按工作目录分会话
- PowerShell stderr 报 `NativeCommandError` 不影响实际执行（git push 等成功也报）
- `paper-creator` 用的是 `gradpen`，新版 `paper-generator` 用的是 `paperpass`
