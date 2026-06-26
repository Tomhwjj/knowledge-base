"""
RAG 查询隐式改写 — 从上下文提取关键词，拼入原 query。
Claude 调用 query.py 前自动跑这个，对用户透明。

用法:
  python query_rewrite.py "原始问题" --context "当前对话上下文..."

输出改写后的完整 query 字符串，供 query.py 使用。
"""
import sys
import re

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def extract_keywords(text: str) -> list[str]:
    """从上下文中提取关键信息"""
    keywords = []

    # 技术栈关键词（不依赖 \b，中文文本中无单词边界）
    tech_terms = [
        'ChromaDB', 'Milvus', 'BGE', 'MiniLM', 'BM25', 'jieba',
        'pdfplumber', 'PyMuPDF', 'Obsidian', 'RAG', 'RRF', 'Reranker',
        'Cross-Encoder', 'sentence-transformers', 'HuggingFace', 'Playwright',
        'Claude Code', 'vaultrag', 'knowledge-base',
    ]
    for term in tech_terms:
        if term.lower() in text.lower():
            keywords.append(term)

    # 标签过滤权重
    decision_words = ('决策', '约束', '规范', '禁止', '架构', '方案', '选型')
    issue_words = ('bug', 'Bug', '报错', '错误', '失败', '坑', '异常')
    task_words = ('待办', '进度', '任务', '下一步')

    if any(w in text for w in decision_words):
        keywords.append("mem-decision mem-rule")
    if any(w in text for w in issue_words):
        keywords.append("mem-issue")
    if any(w in text for w in task_words):
        keywords.append("mem-task")

    return list(set(keywords))


def rewrite(query: str, context: str = "") -> str:
    """改写 query：{原问题} {权重标签} {提取的关键词}"""
    parts = [query]

    # 添加标签过滤权重
    tags = extract_keywords(context + " " + query)
    if tags:
        parts.append(" ".join(tags))

    return " ".join(parts)


def main():
    import argparse
    p = argparse.ArgumentParser(description="RAG 查询隐式改写")
    p.add_argument("query", help="原始查询")
    p.add_argument("--context", "-c", default="", help="当前上下文（可选）")
    args = p.parse_args()

    rewritten = rewrite(args.query, args.context)

    # 对用户透明：只输出改写后的 query，不解释
    print(rewritten)


if __name__ == "__main__":
    main()
