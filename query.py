"""
知识库查询脚本 (v3)
- BGE 中文 Embedding（精度 +20%）
- BM25 + 向量 混合检索 + RRF 融合（补上关键词盲区）
- Cross-Encoder Reranker 精排（精度 +30-50%）
- 三阶段检索：双路召回 → RRF 融合 → 精排
"""
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from config import (
    DB_DIR,
    EMBEDDING_MODEL, QUERY_INSTRUCTION,
    RERANKER_MODEL,
    TOP_K, RERANK_MULTIPLIER, RRF_K,
)
import chromadb
from sentence_transformers import SentenceTransformer, CrossEncoder


# ═══════════════════════════════════════════════
# BM25 索引
# ═══════════════════════════════════════════════

def _build_bm25(collection):
    """从 ChromaDB 的所有文档构建 BM25 索引"""
    try:
        import jieba
    except ImportError:
        print("[WARN] jieba 未安装，BM25 关键词检索将跳过")
        print("       安装: pip install jieba")
        return None, None, None

    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        print("[WARN] rank_bm25 未安装，BM25 关键词检索将跳过")
        print("       安装: pip install rank-bm25")
        return None, None, None

    # 取出所有文档
    all_data = collection.get()
    if not all_data["ids"]:
        return None, None, None

    docs = all_data["documents"]
    ids = all_data["ids"]
    metas = all_data["metadatas"]

    # jieba 分词
    tokenized = [list(jieba.cut(doc)) for doc in docs]
    bm25 = BM25Okapi(tokenized)

    return bm25, docs, ids, metas


# ═══════════════════════════════════════════════
# 初始化
# ═══════════════════════════════════════════════

def _find_latest_collection(chroma_client) -> str:
    """找到最新的 knowledge_ 集合"""
    cols = [c.name for c in chroma_client.list_collections()
            if c.name.startswith("knowledge_")]
    if not cols:
        raise RuntimeError("向量库为空，请先运行 ingest.py")
    return sorted(cols)[-1]


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

# 构建 BM25 索引
print(f"BM25 ...", end=" ", flush=True)
_bm25_result = _build_bm25(collection)
if _bm25_result[0] is not None:
    bm25, all_ids, all_docs, all_metas = _bm25_result
    id_to_idx = {doc_id: idx for idx, doc_id in enumerate(all_ids)}
    print(f"({len(all_ids)} 篇文档)", end=" ", flush=True)
    has_bm25 = True
else:
    has_bm25 = False

print("就绪\n")


# ═══════════════════════════════════════════════
# RRF 融合
# ═══════════════════════════════════════════════

def rrf_fusion(
    vector_ranked: list[dict],
    bm25_ranked: list[dict],
    k: int = RRF_K,
) -> list[str]:
    """
    Reciprocal Rank Fusion: 把两条检索路的排名融合成一个。

    不关心各自打分的绝对数值（向量距离和 BM25 分的量纲不同），
    只看排名 —— 两条路都排前面的文档 RRF 分最高。
    """
    scores: dict[str, float] = {}

    for rank, r in enumerate(vector_ranked):
        doc_id = r["id"]
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)

    for rank, r in enumerate(bm25_ranked):
        doc_id = r["id"]
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)

    # 按 RRF 分数降序排列
    sorted_ids = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [doc_id for doc_id, _ in sorted_ids]


# ═══════════════════════════════════════════════
# 三阶段检索
# ═══════════════════════════════════════════════

def retrieve(query: str, top_k: int = TOP_K) -> list[dict]:
    """
    三阶段检索:
      阶段1: 向量 + BM25 双路召回
      阶段2: RRF 融合排序
      阶段3: Cross-Encoder Reranker 精排
    """
    fetch_k = min(top_k * RERANK_MULTIPLIER, collection.count())

    # ── 路1: 向量检索 ──
    query_with_prefix = QUERY_INSTRUCTION + query
    q_emb = embed_model.encode([query_with_prefix]).tolist()
    vec_results = collection.query(query_embeddings=q_emb, n_results=fetch_k)

    vector_ranked = []
    if vec_results["ids"] and vec_results["ids"][0]:
        for i in range(len(vec_results["ids"][0])):
            vector_ranked.append({
                "id":       vec_results["ids"][0][i],
                "document": vec_results["documents"][0][i],
                "metadata": vec_results["metadatas"][0][i],
                "distance": vec_results["distances"][0][i],
            })

    # ── 路2: BM25 关键词检索 ──
    bm25_ranked = []
    if has_bm25:
        try:
            import jieba
            tokenized_q = list(jieba.cut(query))
            bm25_scores = bm25.get_scores(tokenized_q)
            # 取 top fetch_k
            indexed = list(enumerate(bm25_scores))
            indexed.sort(key=lambda x: x[1], reverse=True)
            for idx, score in indexed[:fetch_k]:
                if score <= 0:
                    continue
                bm25_ranked.append({
                    "id":       all_ids[idx],
                    "document": all_docs[idx],
                    "metadata": all_metas[idx],
                    "bm25_score": float(score),
                })
        except Exception:
            pass

    # ── RRF 融合 ──
    merged_ids = rrf_fusion(vector_ranked, bm25_ranked)

    # 建立 doc_id → 详情 的映射
    doc_map = {}
    for r in vector_ranked:
        doc_map[r["id"]] = r
    for r in bm25_ranked:
        if r["id"] not in doc_map:
            doc_map[r["id"]] = r

    # 取融合后的 top candidates
    candidates = [doc_map[doc_id] for doc_id in merged_ids[:fetch_k] if doc_id in doc_map]

    if not candidates:
        return []

    # ── Cross-Encoder 精排 ──
    pairs = [[query, c["document"]] for c in candidates]
    rerank_scores = reranker.predict(pairs, show_progress_bar=False)

    for c, score in zip(candidates, rerank_scores):
        c["rerank_score"] = float(score)

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
        vec_score = 1 / (1 + r.get("distance", 1.0))
        rerank = r["rerank_score"]

        # 显示每条结果来自哪条检索路
        sources = []
        if "distance" in r:
            sources.append("向量")
        if "bm25_score" in r:
            sources.append(f"BM25:{r['bm25_score']:.1f}")
        source_tag = "+".join(sources) if sources else "融合"

        preview = r["document"][:250].replace("\n", " ") + ("..." if len(r["document"]) > 250 else "")

        print(f"  [{i+1}] [{source}]  精排: {rerank:.4f} | {source_tag}")
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
