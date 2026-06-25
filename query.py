"""
知识库查询脚本 (v2)
- BGE 中文 Embedding（精度 +20%）
- Cross-Encoder Reranker（精度再 +30-50%）
- 两阶段检索：粗筛 → 精排
"""
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from config import (
    DB_DIR,
    EMBEDDING_MODEL, QUERY_INSTRUCTION,
    RERANKER_MODEL,
    TOP_K, RERANK_MULTIPLIER,
)
import chromadb
from sentence_transformers import SentenceTransformer, CrossEncoder


# ═══════════════════════════════════════════════
# 初始化
# ═══════════════════════════════════════════════

def _find_latest_collection(chroma_client) -> str:
    """找到最新的 knowledge_ 集合"""
    cols = [c.name for c in chroma_client.list_collections()
            if c.name.startswith("knowledge_")]
    if not cols:
        raise RuntimeError("向量库为空，请先运行 ingest.py")
    return sorted(cols)[-1]  # 时间戳排序，取最新


print(f"加载 Embedding: {EMBEDDING_MODEL} ...", end=" ", flush=True)
embed_model = SentenceTransformer(EMBEDDING_MODEL)

chroma = chromadb.PersistentClient(path=DB_DIR)
try:
    collection_name = _find_latest_collection(chroma)
    collection = chroma.get_collection(name=collection_name)
except RuntimeError:
    print(f"\n[ERROR] 向量库为空。请先导入文档:")
    print(f"  python ingest.py")
    sys.exit(1)

print(f"({collection_name})", end=" ", flush=True)

print(f"Reranker: {RERANKER_MODEL} ...", end=" ", flush=True)
reranker = CrossEncoder(RERANKER_MODEL)

print(f"就绪 ({collection.count()} 块)\n")


# ═══════════════════════════════════════════════
# 两阶段检索
# ═══════════════════════════════════════════════

def retrieve(query: str, top_k: int = TOP_K) -> list[dict]:
    """
    两阶段检索:
      阶段1: 向量相似度粗筛 top_k * N 条
      阶段2: Cross-Encoder Reranker 精排，取 top_k
    """
    # ── 阶段1: 向量粗筛 ──
    query_with_prefix = QUERY_INSTRUCTION + query
    q_emb = embed_model.encode([query_with_prefix]).tolist()
    fetch_k = min(top_k * RERANK_MULTIPLIER, collection.count())

    results = collection.query(query_embeddings=q_emb, n_results=fetch_k)

    if not results["ids"] or not results["ids"][0]:
        return []

    candidates = []
    for i in range(len(results["ids"][0])):
        candidates.append({
            "id":       results["ids"][0][i],
            "document": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i],
        })

    # ── 阶段2: Cross-Encoder 精排 ──
    pairs = [[query, c["document"]] for c in candidates]
    rerank_scores = reranker.predict(pairs, show_progress_bar=False)

    for c, score in zip(candidates, rerank_scores):
        c["rerank_score"] = float(score)

    # 按 reranker 分数降序，取 top_k
    candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
    return candidates[:top_k]


# ═══════════════════════════════════════════════
# 交互 / 单次查询
# ═══════════════════════════════════════════════

def format_results(query: str, results: list[dict]):
    """格式化输出检索结果"""
    print(f"\n{'='*60}")
    print(f"[Q] {query}\n")

    if not results:
        print("  (没有找到相关内容)")
        return

    for i, r in enumerate(results):
        source = r["metadata"].get("source", "?")
        char_count = r["metadata"].get("char_count", "?")
        vec_score = 1 / (1 + r["distance"])
        rerank = r["rerank_score"]
        preview = r["document"][:250].replace("\n", " ") + ("..." if len(r["document"]) > 250 else "")

        print(f"  [{i+1}] [{source}]  粗排: {vec_score:.0%} | 精排: {rerank:.4f}")
        print(f"      {preview}")
        print()


if len(sys.argv) > 1:
    query = " ".join(sys.argv[1:])
    results = retrieve(query)
    format_results(query, results)
else:
    print("输入问题，或 'quit' 退出\n")
    while True:
        try:
            q = input("Query: ").strip()
            if not q:
                continue
            if q.lower() in ("quit", "exit", "q"):
                print("Bye!")
                break
            results = retrieve(q)
            format_results(q, results)
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break
