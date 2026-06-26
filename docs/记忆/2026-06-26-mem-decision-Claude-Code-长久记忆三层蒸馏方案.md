---
tags: [mem-decision, mem-rule, hot-30d]
date: 2026-06-26
summary: 记忆蒸馏三层: CLAUDE.md提示级自动提醒 + Stop Hook会话结束写草稿 + lifecycle/health定时维护。dream_trigger因价值不足移除。knowledge-base是运行引擎，vaultrag是GitHub发布版。DOC_DIR直接指向Obsidian vault零复制。
---

# Claude Code 长久记忆三层蒸馏方案

## 📌 结论
CC长久记忆蒸馏三层落地: ①CLAUDE.md每10轮/话题切换自动建议/digest ②settings.json Stop Hook会话结束自动写草稿到vault ③lifecycle(每日)health(每周)定时维护。vaultrag v1.2发布GitHub，定位从RAG引擎升级为AI记忆栈。

## 🧭 决策
1. knowledge-base=运行引擎, vaultrag=GitHub发布版, 职责分离
2. DOC_DIR直接指Obsidian vault, 写入即入库, 零复制
3. dream_trigger 4小时巡检价值不足, 砍掉
4. /digest写入→自动incremental_ingest, 一条命令完成
5. Obsidian vault路径: D:\\Agent\\Obsidian store
6. 记忆文件命名: {date}-{tag}-{slug}.md, 存vault /记忆/
7. Token预算: 60K/200K, 22篇快照上限
8. vaultrag README用完整架构文档替代, 12条原方案全覆盖

## 🔒 约束
1. 禁止设HTTP_PROXY/HTTPS_PROXY环境变量
2. 模型文件放项目内models/, 不散落C盘
3. 自建skill不备份到vercel-skills
4. HF_HUB_OFFLINE=1, 模型缓存禁止联网
5. .COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.PY;.PYW;.CPL doesn't support this operation
6. vault中的.kbignore控制索引范围

## 🐛 问题
1. git残留代理33210端口导致push超时→清除
2. sentence_transformers加载时联网校验→HF_HUB_OFFLINE=1
3. 子目录文件不入库→递归walk_files修复
4. ChromaDB ID含路径分隔符→safe_name替换
5. 小说下载脚本扔/tmp→封装为novel-downloader skill+通用工具
6. Stop Hook拿不到完整对话内容→当前方案写草稿标记, 需Claude后续确认

## 📎 来源
- 对话日期: 2026-06-26
