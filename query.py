"""
知识库查询脚本
用自然语言提问，从本地文档中搜索答案
"""
import os
import sys

# 强制 UTF-8 输出，避免 Windows GBK 乱码
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 国内用户用 HuggingFace 镜像加速
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import chromadb
from sentence_transformers import SentenceTransformer

# ── 配置 ────────────────────────────────────
DB_DIR = os.path.join(os.path.dirname(__file__), "vectordb")
MODEL  = "paraphrase-multilingual-MiniLM-L12-v2"
TOP_K  = 5

# ── 初始化 ──────────────────────────────────
print(f"Loading model...", end=" ", flush=True)
model = SentenceTransformer(MODEL)

chroma = chromadb.PersistentClient(path=DB_DIR)
try:
    collection = chroma.get_collection(name="knowledge")
except Exception:
    print(f"\n[ERROR] Vector DB is empty. Run ingest.py first:")
    print(f"  python ingest.py")
    sys.exit(1)

print(f"Ready ({collection.count()} chunks)\n")

# ── 查询 ────────────────────────────────────
if len(sys.argv) > 1:
    queries = [" ".join(sys.argv[1:])]
else:
    print("Type your question, or 'quit' to exit\n")
    queries = []
    while True:
        try:
            q = input("Query: ").strip()
            if not q:
                continue
            if q.lower() in ("quit", "exit", "q"):
                print("Bye!")
                break
            queries.append(q)
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

for query in queries:
    print(f"\n{'='*60}")
    print(f"[Q] {query}\n")

    q_emb = model.encode([query]).tolist()
    results = collection.query(query_embeddings=q_emb, n_results=TOP_K)

    if not results["ids"] or not results["ids"][0]:
        print("  (No relevant content found)")
        continue

    for i, (doc_id, doc_text, meta, distance) in enumerate(
        zip(results["ids"][0], results["documents"][0], results["metadatas"][0], results["distances"][0])
    ):
        score = 1 / (1 + distance)
        source = meta.get("source", "?")
        preview = doc_text[:200].replace("\n", " ") + ("..." if len(doc_text) > 200 else "")
        print(f"  [{i+1}] [{source}]  relevance: {score:.0%}")
        print(f"      {preview}")
        print()
