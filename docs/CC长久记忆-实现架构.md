---
tags: [mem-decision, mem-rule, hot-30d]
date: 2026-06-26
summary: Claude Code 长久记忆系统的完整实现架构——三层边界、文件规范、脚本清单、冷启动流程
---

# Claude Code 长久记忆 — 实现架构

## 一、三层边界

```
┌──────────────────────────────────────────────┐
│  Layer 1: CLAUDE.md 指令                     │
│  启动加载 / 水位判断 / 检索改写 / /digest     │
│  靠 Claude 自身推理执行，不调外部脚本          │
├──────────────────────────────────────────────┤
│  Layer 2: Python 脚本                        │
│  memory_load.py / memory_digest.py /          │
│  lifecycle.py / dedup.py                     │
│  Claude 通过 Bash 调用，复用现有 RAG 管线      │
├──────────────────────────────────────────────┤
│  Layer 3: 后台 Cron                          │
│  生命周期升降级 / 健康度监控 / Dream触发       │
│  独立于 Claude Code，系统定时任务              │
└──────────────────────────────────────────────┘
```

---

## 二、记忆文件规范

### 文件名

```
{YYYY-MM-DD}-{tag}-{slug}.md

示例:
  2026-06-26-mem-decision-rag-three-way.md
  2026-06-25-mem-rule-no-proxy-env-vars.md
  2026-06-24-mem-issue-git-stale-proxy-port.md
  2026-06-26-mem-task-investment-brain-mvp.md
```

### 存放位置

Obsidian vault 根目录下 `/记忆/` 子目录（可选，便于浏览），KB 递归扫描自动索引。

### 强制 Frontmatter

```yaml
---
tags: [mem-decision, mem-rule, hot-30d]   # 至少一个内容标签 + 一个时效标签
date: 2026-06-26
summary: 一句话结论（用于 RAG 检索和列表展示）
related:                                 # 可选，关联的 vault 文件
  - "[[投资智囊项目搭建]]"
  - "[[2026-06-25 项目日志]]"
---
```

### 正文模板

```markdown
# <记忆标题>

## 📌 结论
<一句话总结，这是 RAG 检索命中后展示的摘要>

## 🧭 决策
- 选择 A 方案而非 B 方案
- 原因: ...

## 🔒 约束
- 必须遵守 XXX
- 禁止 XXX

## 🐛 问题
- 现象: ...
- 根因: ...
- 解决: ...

## 📎 来源
- 对话日期: 2026-06-26
- 相关笔记: [[...]]
```

---

## 三、Layer 1 — CLAUDE.md 指令

### 3.1 启动加载（每次会话开始）

```
启动时执行:
  1. 扫描 vault 中 tags 包含 #hot-30d 的 .md 文件
  2. 按优先级排序: #mem-rule > #mem-decision > #mem-issue > #mem-task
  3. 逐个加载全文，累计 token 估算（1 字符 ≈ 0.3 token）
  4. 当累计 > 上下文窗口 30% 时停止加载更多文件
  5. 剩余 #hot 文件记录标题和 summary，不加载全文
  6. 加载的文本插入到 system prompt 之后、对话之前
```

### 3.2 水位判断（每次用户消息后）

```
每轮对话后检查:
  estimated_tokens = (已加载记忆字符数 × 0.3) + (对话字符数 × 0.3)
  threshold = 上下文窗口 × 0.7

  if estimated_tokens > threshold:
    → 卸载已加载的记忆全文
    → 以当前 query 触发 RAG 检索:
        python D:\Agent\git\knowledge-base\query.py "<改写后的query>"
    → 召回 Top 6-8 片段插入上下文
    → 标记当前为 RAG 模式
  else:
    → 保持全文加载模式
```

### 3.3 RAG 查询改写

```
触发 RAG 检索前:
  1. 从当前对话提取关键词: 项目名、模块名、技术栈、错误信息
  2. 改写 query = "{用户原问题} {标签过滤:mem-decision,mem-rule,mem-issue} {提取的关键词}"
  3. 静默执行，不告知用户
```

### 3.4 /digest 命令

```
用户输入 /digest 时:
  1. 扫描本次对话，提取: 决策、约束、问题、结论
  2. 丢弃: 闲聊、情绪、试探性讨论
  3. 确定标签（内容类型 + 时效等级）
  4. 按模板格式化
  5. 调用 Layer 2 的 memory_digest.py 做去重检查
  6. 写入 vault 记忆文件
  7. 执行 incremental_ingest
  8. 从当前上下文删除已蒸馏的对话段落
```

### 3.5 冲突处理

```
如果 RAG 召回的片段与当前指令矛盾:
  1. 在回复开头显式标注: ⚠️ 与历史记录冲突: {简述}
  2. 按当前指令执行
  3. 建议用户用 /digest 更新历史记忆
```

---

## 四、Layer 2 — Python 脚本

### 4.1 memory_load.py — 启动记忆加载器

```
输入: vault 路径
输出: JSON（文件名、title、summary、tags、全文前 500 字符）

工作:
  1. 扫描 vault 所有 .md 的 frontmatter
  2. 筛选 tags 含 #hot-30d 的文件
  3. 按优先级排序
  4. 返回结构化列表

Claude 调用方式:
  python D:\Agent\git\knowledge-base\memory_load.py
```

### 4.2 memory_digest.py — 去重检查 + 写入

```
输入: 新记忆的 title + summary + tags
输出: {action: "create"|"merge", file: "路径"}

工作:
  1. 扫描已有 #hot-30d 文件
  2. 用 BGE 对 summary 做向量编码
  3. 与已有文件的 summary 做余弦相似度
  4. > 0.85: 返回 merge 建议（旧文件路径）
  5. ≤ 0.85: 返回 create

Claude 调用方式:
  python D:\Agent\git\knowledge-base\memory_digest.py \
    --title "xxx" --summary "xxx" --tags "mem-decision,hot-30d"
```

### 4.3 lifecycle.py — 生命周期升降级

```
工作:
  1. 扫描 vault 所有记忆文件的 frontmatter date 和 tags
  2. #hot-30d 且 date > 30 天 → 降为 #warm-90d
  3. #warm-90d 且 date > 90 天 → 降为 #cold-arch
  4. 检查 RAG 调用日志: cold-arch 被召回 ≥ 3 次/月 → 升为 #warm-90d
  5. 更新文件 frontmatter
  6. 输出变更日志

调用方式（cron 每日一次）:
  python D:\Agent\git\knowledge-base\lifecycle.py
```

### 4.4 现有脚本复用

| 现有脚本 | 在记忆系统中的角色 |
|------|------|
| `query.py` | Layer 1 水位超限时触发 RAG 检索 |
| `incremental_ingest.py` | /digest 写记忆后自动入库 |
| `graph_index.py` | 记忆文件间的 wikilink 图谱 |

---

## 五、Layer 3 — 后台 Cron

```
# 每天凌晨 2:00 — 生命周期升降级
0 2 * * * cd D:\Agent\git\knowledge-base && python lifecycle.py

# 每 4 小时 — Dream Consolidation 触发检查
0 */4 * * * cd D:\Agent\git\knowledge-base && python dream_trigger.py

# 每周日 — 健康度报告
0 3 * * 0 cd D:\Agent\git\knowledge-base && python health_report.py
```

> Windows 用任务计划程序替代 cron。

---

## 六、冷启动引导

### 零记忆的第一个会话

```
1. Claude 启动 → 扫描 vault → 0 个 #hot-30d 文件
2. 正常对话，记忆加载步骤静默跳过
3. 用户说"记住 XXX"或输入 /digest → 创建第一个记忆文件
4. 第二次会话 → 自动加载该文件
5. 记忆从零开始，随使用自然增长
```

### 首次部署

```
1. 确保 vault 路径在 knowledge-base config.py 中配置正确
2. 创建 /记忆/ 子目录（可选）
3. 确保 incremental_ingest.py 可运行
4. 无需预填任何记忆文件——冷启动零配置
```

---

## 七、Token 预算模型

```
基准: Claude Opus 200K 上下文窗口

┌──────────────────┬──────────┬─────────────────┐
│ 区域              │ 占比     │ 实际 token       │
├──────────────────┼──────────┼─────────────────┤
│ System Prompt    │ ~5%      │ ~10K            │
│ 记忆快照 (B+C)    │ ≤30%     │ ≤60K            │
│ 当前对话 (A)      │ 50-55%   │ ~100K-110K      │
│ 预留缓冲          │ 10-15%   │ ~20K            │
├──────────────────┼──────────┼─────────────────┤
│ 合计              │ 100%     │ 200K            │
└──────────────────┴──────────┴─────────────────┘

换算:
  60K token ≈ 45,000 中文字符 ≈ 22 篇标准记忆快照（每篇~2000字）
  → 日常使用中 #hot-30d 快照数控制在 20 篇以内，不会触发水位降级
```

---

## 八、文件清单

```
D:\Agent\git\knowledge-base\
├── memory_load.py          ← 新建: 启动记忆加载
├── memory_digest.py        ← 新建: 去重写入
├── lifecycle.py            ← 新建: 生命周期管理
├── dream_trigger.py        ← 新建: Dream Consolidation 触发
├── health_report.py        ← 新建: 健康度监控
├── query.py                ← 已有: RAG 检索
├── incremental_ingest.py   ← 已有: 增量入库
├── graph_index.py          ← 已有: 图谱
└── config.py               ← 已有: 统一配置

D:\Agent\Obsidian store\
└── 记忆/                    ← 记忆快照存放目录

C:\Users\何伟\.claude\CLAUDE.md  ← 添加记忆加载指令
```

---

## 九、与原方案的对照

| 原方案条款 | 实现方式 | 所在层 |
|------|------|:--:|
| 一、标签体系 | frontmatter tags | 规范 |
| 二、快照模板 | memory_digest.py | L2 |
| 三、上下文调度 | CLAUDE.md 指令 | L1 |
| 四、运行三阶段 | CLAUDE.md 指令 | L1 |
| 五、蒸馏双通道 | /digest (L1) + Dream (L3) | L1+L3 |
| 六、插回规则 | /digest --inject | L1 |
| 七、生命周期 | lifecycle.py | L3 |
| 八、查询改写 | CLAUDE.md 指令 | L1 |
| 九、冲突处理 | CLAUDE.md 指令 | L1 |
| 十、去重合并 | memory_digest.py | L2 |
| 十一、降级保护 | CLAUDE.md 指令 | L1 |
| 十二、健康监控 | health_report.py | L3 |
