"""
知识库常驻查询服务 (v1)
- 启动时一次性加载 BGE + Reranker + BM25 + 图谱
- 常驻内存，HTTP API 毫秒级查询
- 30 分钟无查询自动退出（可通过 --no-idle 禁用）
- 零外部依赖（只用 stdlib）

用法:
  python kb_server.py                  # 前台运行，30min 空闲退出
  python kb_server.py --no-idle        # 永不空闲退出
  python kb_server.py --port 8765      # 指定端口
"""
import json
import os
import sys
import time
import math
import threading
import re
import datetime
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """多线程 HTTP 服务器，避免慢查询阻塞后续请求"""
    daemon_threads = True

# ── 路径 ────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from config import (
    DB_DIR, EMBEDDING_MODEL, QUERY_INSTRUCTION,
    RERANKER_MODEL, TOP_K, RERANK_MULTIPLIER, RRF_K,
)
try:
    from config import RRF_WEIGHTS
except ImportError:
    RRF_WEIGHTS = None

# ── 全局状态（启动时加载） ──────────────────
embed_model = None
reranker = None
collection = None
bm25 = None
all_ids = None
all_docs = None
all_metas = None
has_bm25 = False
graph = None
has_graph = False
start_time = None
last_query_time = None
IDLE_TIMEOUT = 1800  # 30 分钟


def load_models():
    """一次性加载所有模型和索引"""
    global embed_model, reranker, collection
    global bm25, all_ids, all_docs, all_metas, has_bm25
    global graph, has_graph, start_time, last_query_time

    start_time = time.time()
    last_query_time = start_time

    import chromadb
    from sentence_transformers import SentenceTransformer, CrossEncoder

    # ── Embedding ──
    print(f"[kb-server] 加载 Embedding: {EMBEDDING_MODEL} ...", end=" ", flush=True)
    embed_model = SentenceTransformer(EMBEDDING_MODEL)
    t1 = time.time()
    print(f"({t1 - start_time:.1f}s)")

    # ── ChromaDB ──
    print(f"[kb-server] 连接 ChromaDB: {DB_DIR} ...", end=" ", flush=True)
    chroma = chromadb.PersistentClient(path=DB_DIR)
    cols = [c.name for c in chroma.list_collections() if c.name.startswith("knowledge_")]
    if not cols:
        print("\n[ERROR] 向量库为空，请先运行 python ingest.py")
        sys.exit(1)
    collection_name = sorted(cols)[-1]
    collection = chroma.get_collection(name=collection_name)
    print(f"({collection_name}, {collection.count()} chunks)")

    # ── Reranker ──
    print(f"[kb-server] 加载 Reranker: {RERANKER_MODEL} ...", end=" ", flush=True)
    reranker = CrossEncoder(RERANKER_MODEL)
    t2 = time.time()
    print(f"({t2 - t1:.1f}s)")

    # ── BM25 ──
    print(f"[kb-server] 构建 BM25 索引 ...", end=" ", flush=True)
    try:
        import jieba
        from rank_bm25 import BM25Okapi

        all_data = collection.get()
        if all_data["ids"]:
            all_ids = all_data["ids"]
            all_docs = all_data["documents"]
            all_metas = all_data["metadatas"]
            tokenized = [list(jieba.cut(doc)) for doc in all_docs]
            bm25 = BM25Okapi(tokenized)
            has_bm25 = True
            print(f"({len(all_ids)} 篇)")
        else:
            has_bm25 = False
            print("(无文档)")
    except ImportError as e:
        print(f"(跳过: {e})")
        has_bm25 = False

    # ── 图谱 ──
    print(f"[kb-server] 加载图谱 ...", end=" ", flush=True)
    try:
        from graph_index import load_graph as _load_graph, expand_candidates
        graph = _load_graph()
        if graph:
            has_graph = True
            print(f"({graph.get('file_count', '?')} 节点)")
        else:
            has_graph = False
            print("(未构建)")
    except Exception as e:
        print(f"(跳过: {e})")
        has_graph = False

    elapsed = time.time() - start_time
    print(f"[kb-server] ✅ 全部就绪 ({elapsed:.1f}s)")

    # ── 预热：跑一次空查询，让 ChromaDB / Embedding / BM25 进入热缓存 ──
    print(f"[kb-server] 预热中 ...", end=" ", flush=True)
    t_warm = time.time()
    try:
        retrieve("__warmup__")  # 触发所有懒加载
        print(f"({time.time() - t_warm:.1f}s)")
    except Exception as e:
        print(f"(跳过: {e})")

    print(f"[kb-server] 端口: {PORT}  |  空闲超时: {'禁用' if NO_IDLE else f'{IDLE_TIMEOUT}s'}")
    print(f"[kb-server] 端点: http://127.0.0.1:{PORT}/query?q=...  |  http://127.0.0.1:{PORT}/health")


# ── Reranker 缓存 ──────────────────────────
# 简单 LRU: key = (query_hash, doc_id), value = score
# 命中后跳过 CrossEncoder 推理，大幅加速重复查询
import hashlib
_rerank_cache: dict[str, float] = {}
_RERANK_CACHE_MAX = 500  # 最多缓存 500 条打分结果

def _extract_keywords(text: str) -> list[str]:
    """三路本地关键词提取"""
    import jieba.analyse

    keywords = []

    # A1: 正则自动词典
    try:
        from memory_load import load as load_memories
        rules = load_memories(hot_only=False)
        rule_text = " ".join([m.get("summary", "") for m in rules
                             if "mem-rule" in m.get("tags", [])])
    except Exception:
        rule_text = ""

    base_terms = [
        'ChromaDB', 'Milvus', 'BGE', 'MiniLM', 'BM25', 'jieba',
        'pdfplumber', 'PyMuPDF', 'Obsidian', 'RAG', 'RRF', 'Reranker',
        'Cross-Encoder', 'sentence-transformers', 'HuggingFace', 'Playwright',
        'Claude Code', 'vaultrag', 'knowledge-base', 'investment-advisor',
    ]
    auto_terms = re.findall(r'[A-Z][a-zA-Z0-9.\-]+[a-zA-Z0-9]', rule_text)
    all_terms = set(base_terms + auto_terms)

    for term in all_terms:
        if term.lower() in text.lower():
            keywords.append(term)

    # A2: TF-IDF
    try:
        keywords.extend([k for k in jieba.analyse.extract_tags(text, topK=6) if len(k) >= 2])
    except Exception:
        pass

    # A3: TextRank
    try:
        keywords.extend([k for k in jieba.analyse.textrank(text, topK=6) if len(k) >= 2])
    except Exception:
        pass

    seen = set()
    merged = []
    for k in keywords:
        if k.lower() not in seen:
            seen.add(k.lower())
            merged.append(k)
    return merged


def rrf_fusion(*routes: list[dict], k: int = RRF_K, weights: list[float] = None) -> list[str]:
    """RRF 多路融合"""
    scores: dict[str, float] = {}
    if weights is None:
        weights = [1.0] * len(routes)

    for route, w in zip(routes, weights):
        for rank, r in enumerate(route):
            doc_id = r["id"]
            scores[doc_id] = scores.get(doc_id, 0.0) + w * 1.0 / (k + rank + 1)

    sorted_ids = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [doc_id for doc_id, _ in sorted_ids]


def retrieve(query: str, top_k: int = TOP_K, fast: bool = False) -> list[dict]:
    """
    三路检索 + RRF 融合 + Reranker 精排。
    fast=True 时跳过 CrossEncoder，直接用 RRF 分数排序（快 10-20 倍）。
    """
    import time as _time
    _t_total = _time.time()
    _timings = {}

    fetch_k = min(top_k * RERANK_MULTIPLIER, collection.count())

    # 阶段0: 关键词增强
    _t0 = _time.time()
    kw = _extract_keywords(query)
    if kw:
        query = query + " " + " ".join(kw)
    _timings["keywords"] = _time.time() - _t0

    # 路1: 向量检索
    _t0 = _time.time()
    query_with_prefix = QUERY_INSTRUCTION + query
    q_emb = embed_model.encode([query_with_prefix]).tolist()
    vec_results = collection.query(query_embeddings=q_emb, n_results=fetch_k)
    _timings["vector"] = _time.time() - _t0

    vector_ranked = []
    if vec_results["ids"] and vec_results["ids"][0]:
        for i in range(len(vec_results["ids"][0])):
            vector_ranked.append({
                "id":       vec_results["ids"][0][i],
                "document": vec_results["documents"][0][i],
                "metadata": vec_results["metadatas"][0][i],
                "distance": vec_results["distances"][0][i],
            })

    # 路2: BM25
    _t0 = _time.time()
    bm25_ranked = []
    if has_bm25:
        try:
            import jieba
            tokenized_q = list(jieba.cut(query))
            bm25_scores = bm25.get_scores(tokenized_q)
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
    _timings["bm25"] = _time.time() - _t0

    # 路3: 图谱扩展
    _t0 = _time.time()
    graph_ranked = []
    if has_graph:
        from graph_index import expand_candidates
        top_sources = set()
        for r in (vector_ranked + bm25_ranked)[:top_k * 2]:
            src = r["metadata"].get("source", "")
            if src:
                top_sources.add(src)

        graph_linked = set()
        for src in top_sources:
            linked = expand_candidates(src, graph)
            graph_linked.update(linked)

        if graph_linked:
            for linked_file in graph_linked:
                try:
                    linked_chunks = collection.get(
                        where={"source": linked_file},
                        limit=top_k,
                    )
                    if linked_chunks["ids"]:
                        for j in range(len(linked_chunks["ids"])):
                            graph_ranked.append({
                                "id":       linked_chunks["ids"][j],
                                "document": linked_chunks["documents"][j],
                                "metadata": linked_chunks["metadatas"][j],
                                "graph_file": linked_file,
                            })
                except Exception:
                    pass

    _timings["graph"] = _time.time() - _t0

    # RRF 融合
    _t0 = _time.time()
    merged_ids = rrf_fusion(vector_ranked, bm25_ranked, graph_ranked,
                            weights=RRF_WEIGHTS)

    doc_map = {}
    for r in vector_ranked:
        doc_map[r["id"]] = r
    for r in bm25_ranked:
        if r["id"] not in doc_map:
            doc_map[r["id"]] = r
    for r in graph_ranked:
        if r["id"] not in doc_map:
            doc_map[r["id"]] = r

    candidates = [doc_map[doc_id] for doc_id in merged_ids[:fetch_k] if doc_id in doc_map]

    _timings["rrf+merge"] = _time.time() - _t0

    if not candidates:
        return []

    # Reranker 精排（支持 fast 跳过 + 缓存加速）
    _t0 = _time.time()

    if fast:
        # 快速模式：直接用 RRF 融合分数，不做 CrossEncoder
        rrf_scores = {}
        for route_idx, route in enumerate([vector_ranked, bm25_ranked, graph_ranked]):
            w = (RRF_WEIGHTS or [1.0]*3)[route_idx]
            for rank, r in enumerate(route):
                doc_id = r["id"]
                rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + w * 1.0 / (RRF_K + rank + 1)
        for c in candidates:
            c["rerank_score"] = rrf_scores.get(c["id"], 0.0)
    else:
        # 标准模式：CrossEncoder 精排（带缓存）
        query_hash = hashlib.md5(query.encode()).hexdigest()[:12]
        pairs = []
        cache_hits = []
        for c in candidates:
            cache_key = f"{query_hash}:{c['id']}"
            if cache_key in _rerank_cache:
                cache_hits.append((c, _rerank_cache[cache_key]))
            else:
                pairs.append((c, [query, c["document"]]))

        # 缓存命中 → 直接赋值
        for c, score in cache_hits:
            c["rerank_score"] = score

        # 缓存未命中 → CrossEncoder 推理
        if pairs:
            uncached_candidates, uncached_pairs = zip(*pairs)
            uncached_scores = reranker.predict(list(uncached_pairs), show_progress_bar=False)
            for c, score in zip(uncached_candidates, uncached_scores):
                cache_key = f"{query_hash}:{c['id']}"
                if len(_rerank_cache) < _RERANK_CACHE_MAX:
                    _rerank_cache[cache_key] = float(score)
                c["rerank_score"] = float(score)

    _timings["reranker"] = _time.time() - _t0
    _t0 = _time.time()

    # 时间衰减（fast 模式也做，基于 RRF 分数）
    for c in candidates:
        mem_date = c.get("metadata", {}).get("date", "")
        if not mem_date:
            try:
                src = c.get("metadata", {}).get("source", "")
                if src:
                    match = re.search(r'(\d{4}-\d{2}-\d{2})', src)
                    if match:
                        mem_date = match.group(1)
            except Exception:
                pass
        if mem_date:
            try:
                d = datetime.date.fromisoformat(mem_date)
                age = (datetime.date.today() - d).days
                decay = math.exp(-0.023 * age)
                c["rerank_score"] = float(c["rerank_score"]) * decay
            except ValueError:
                pass

    candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
    result = candidates[:top_k]

    _timings["decay+sort"] = _time.time() - _t0
    _timings["total"] = _time.time() - _t_total
    # 只在耗时 >1s 时打印（避免正常快速查询刷屏）
    if _timings["total"] > 1.0:
        _parts = ", ".join(f"{k}:{v:.1f}s" for k, v in _timings.items())
        print(f"[kb-server] ⏱ 慢查询 ({_timings['total']:.1f}s) → {_parts}", flush=True)

    return result


# ═══════════════════════════════════════════════
# HTTP Handler
# ═══════════════════════════════════════════════

class KBHandler(BaseHTTPRequestHandler):
    """轻量 HTTP API handler"""

    def log_message(self, format, *args):
        """精简日志"""
        global last_query_time
        last_query_time = time.time()
        print(f"[kb-server] {self.address_string()} - {format % args}")

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/health":
            self._send_json({
                "status": "ok",
                "uptime_seconds": round(time.time() - start_time, 1),
                "model": EMBEDDING_MODEL,
                "collection": collection.name if collection else None,
                "chunks": collection.count() if collection else 0,
                "bm25": has_bm25,
                "graph": has_graph,
            })

        elif parsed.path == "/query":
            params = urllib.parse.parse_qs(parsed.query)
            q = params.get("q", [""])[0].strip()
            top_k = int(params.get("top_k", [str(TOP_K)])[0])
            fast = params.get("fast", ["0"])[0] in ("1", "true", "yes")

            if not q:
                self._send_json({"error": "缺少 q 参数"}, 400)
                return

            t0 = time.time()
            results = retrieve(q, top_k, fast=fast)
            elapsed = time.time() - t0

            # 精简输出（去掉大段 document 文本，只保留前 200 字符预览）
            slim_results = []
            for r in results:
                slim = {
                    "rank": r.get("rerank_score", 0),
                    "score": round(r.get("rerank_score", 0), 4),
                    "source": r.get("metadata", {}).get("source", "?"),
                    "preview": r.get("document", "")[:200].replace("\n", " "),
                }
                # 标记来源路径
                paths = []
                if "distance" in r: paths.append("vector")
                if "bm25_score" in r: paths.append("bm25")
                if "graph_file" in r: paths.append("graph")
                slim["paths"] = paths
                slim_results.append(slim)

            self._send_json({
                "query": q,
                "time_ms": round(elapsed * 1000, 1),
                "total_hits": len(results),
                "results": slim_results,
            })

        elif parsed.path == "/shutdown":
            self._send_json({"message": "shutting down..."})
            # 在另一个线程关闭服务器，避免阻塞当前响应
            threading.Thread(target=self.server.shutdown, daemon=True).start()

        else:
            self._send_json({"error": "not found", "endpoints": ["/health", "/query?q=...", "/shutdown"]}, 404)

    do_POST = do_GET  # 兼容 POST


# ═══════════════════════════════════════════════
# 空闲退出 watchdog
# ═══════════════════════════════════════════════

def idle_watchdog():
    """后台线程：超时自动退出"""
    global last_query_time
    while True:
        time.sleep(60)
        if NO_IDLE:
            continue
        idle = time.time() - last_query_time
        if idle > IDLE_TIMEOUT:
            print(f"\n[kb-server] 空闲 {idle:.0f}s 超过 {IDLE_TIMEOUT}s，自动退出")
            os._exit(0)


# ═══════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════

PORT = 8765
NO_IDLE = False

if __name__ == "__main__":
    # 解析参数
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--port" and i + 1 < len(args):
            PORT = int(args[i + 1])
            i += 2
        elif args[i] == "--no-idle":
            NO_IDLE = True
            i += 1
        elif args[i] in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        else:
            print(f"未知参数: {args[i]}, 用 --help 查看帮助")
            sys.exit(1)

    load_models()

    # 启动空闲 watchdog
    if not NO_IDLE:
        threading.Thread(target=idle_watchdog, daemon=True).start()

    server = ThreadingHTTPServer(("127.0.0.1", PORT), KBHandler)
    print(f"[kb-server] 监听 http://127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[kb-server] 收到中断信号，退出")
        server.shutdown()
