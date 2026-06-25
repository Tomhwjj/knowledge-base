"""
知识库统一配置
所有可调参数集中在这里，ingest.py 和 query.py 共用
"""
import os

# ── 路径 ────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOC_DIR = os.path.join(BASE_DIR, "docs")
DB_DIR  = os.path.join(BASE_DIR, "vectordb")

# ── Embedding 模型 ──────────────────────────
# BGE 中文模型，比 MiniLM 对中文的理解好 20%+
# base 版 ~400MB，首次下载需要几分钟
# 备选: "BAAI/bge-large-zh-v1.5" (~1.3GB, 精度最高)
#       "BAAI/bge-small-zh-v1.5" (~95MB, 轻量快速)
EMBEDDING_MODEL = "BAAI/bge-base-zh-v1.5"

# BGE 查询指令前缀（v1.5 large 必需，base/small 加了也不影响）
QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："

# ── Reranker 模型 ───────────────────────────
# Cross-Encoder 重排序，检索后精排，精度提升 30-50%
# "BAAI/bge-reranker-base" ~1GB
# "BAAI/bge-reranker-v2-m3" ~2.2GB, 多语言最强
RERANKER_MODEL = "BAAI/bge-reranker-base"

# ── 分块策略 ────────────────────────────────
CHUNK_SIZE = 800          # 目标块大小（字符数）
CHUNK_OVERLAP = 100       # 相邻块重叠量
# 分割优先级：段落 → 换行 → 句号 → 分号 → 逗号 → 空格 → 字符
SEPARATORS = ["\n\n", "\n", "。", ".", "；", ";", "，", ",", " ", ""]

# ── 检索参数 ────────────────────────────────
TOP_K = 5                 # 最终返回的结果数
RERANK_MULTIPLIER = 3     # 初检召回 top_k * N 条，然后 reranker 精排

# ── 国内镜像（加速模型下载）─────────────────
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
