"""
知识库统一配置
所有可调参数集中在这里，ingest.py 和 query.py 共用
"""
import os

# ── 路径 ────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOC_DIR = r"D:\Agent\Obsidian store"
DB_DIR  = os.path.join(BASE_DIR, "vectordb")

# ── Embedding 模型 ──────────────────────────
EMBEDDING_MODEL = "BAAI/bge-base-zh-v1.5"
QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："

# ── Reranker 模型 ───────────────────────────
RERANKER_MODEL = "BAAI/bge-reranker-base"

# ── 分块策略 ────────────────────────────────
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
SEPARATORS = ["\n\n", "\n", "。", ".", "；", ";", "，", ",", " ", ""]

# ── 检索参数 ────────────────────────────────
TOP_K = 5                   # 最终返回结果数
RERANK_MULTIPLIER = 3       # 每条检索路召回的候选数倍数
RRF_K = 60                  # RRF 融合参数（越大排名影响越平滑）

# ── PDF 解析 ────────────────────────────────
# pdfplumber 能保留表格结构，安装: pip install pdfplumber
# 未安装时自动回退到 PyMuPDF 纯文本提取
USE_PDFPLUMBER = True

# ── HuggingFace 缓存（model/ 目录，跟项目走）──
os.environ["HF_HOME"] = os.path.join(BASE_DIR, "models")
os.environ["HF_HUB_OFFLINE"] = "1"          # 模型已缓存，禁止联网校验
