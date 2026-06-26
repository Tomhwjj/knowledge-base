---
tags: [mem-decision, mem-rule, hot-30d]
date: 2026-06-26
summary: 知识库采用向量+BM25+图谱三路RRF融合检索，模型存项目内，代理不设环境变量，增量入库秒级完成，CC长久记忆分三层架构
---

# VaultRAG 三路检索+长久记忆架构

## 📌 结论
RAG知识库升级到v4三路融合检索（向量+BM25+图谱），模型缓存放项目models/目录，网络不设HTTP_PROXY，GitHub token存~/.git-credentials，增量ingest秒级完成，CC长久记忆分L1(CLAUDE.md)/L2(Python脚本)/L3(Cron)三层

## 🧭 决策
1. Embedding选BAAI/bge-base-zh-v1.5而非MiniLM，中文精度+20%
2. 检索管线: 向量+BM25+图谱→RRF融合→Reranker精排
3. Vault-native架构: Obsidian vault即KB数据源，零复制
4. 增量入库替代全量重建，日常秒级
5. 自建skill不备份到vercel-skills
6. 项目模型文件放项目内，不散落C盘

## 🔒 约束
1. 禁止设HTTP_PROXY/HTTPS_PROXY环境变量，Python/git不走代理
2. Python/git直接走系统VPN TUN模式
3. HF_HUB_OFFLINE=1，模型已缓存禁止联网校验
4. Git全局代理已清除，勿重新设置
5. ChromaDB ID中路径分隔符替换为下划线
6. vault中的.kbignore控制索引范围

## 🐛 问题
1. git残留代理33210端口导致push超时→git config --global --unset http.proxy
2. sentence_transformers加载缓存模型仍联网校验→HF_HUB_OFFLINE=1
3. ChromaDB ID含路径分隔符→safe_name替换
4. 子目录文件不入库→递归walk_files
5. HF镜像hf-mirror.com不可达→系统直连+离线模式

## 📎 来源
- 对话日期: 2026-06-26
