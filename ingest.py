"""
知识库文档导入脚本
把 docs/ 目录下的所有文档（.txt, .md, .pdf）导入本地向量数据库
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
DOC_DIR  = os.path.join(os.path.dirname(__file__), "docs")   # 放文档的地方
DB_DIR   = os.path.join(os.path.dirname(__file__), "vectordb")  # 向量库存储位置
MODEL    = "paraphrase-multilingual-MiniLM-L12-v2"  # 中英双语，首次下载约470MB

# ── 初始化 ──────────────────────────────────
print(f"[1/3] Loading model: {MODEL}")
model = SentenceTransformer(MODEL)

print(f"[2/3] Opening vector DB: {DB_DIR}")
chroma = chromadb.PersistentClient(path=DB_DIR)
collection = chroma.get_or_create_collection(name="knowledge")

# ── 读取文档 ────────────────────────────────
def read_file(filepath: str) -> str | None:
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == ".pdf":
            import fitz
            doc = fitz.open(filepath)
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
            return text
        elif ext in (".txt", ".md"):
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        else:
            return None
    except Exception as e:
        print(f"  [WARN] Failed to read {filepath}: {e}")
        return None

# ── 切分文本 ────────────────────────────────
def chunk_text(text: str, chunk_size: int = 500, overlap: int = 80) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks

# ── 导入流程 ────────────────────────────────
print(f"[3/3] Scanning: {DOC_DIR}")
files = [f for f in os.listdir(DOC_DIR) if os.path.isfile(os.path.join(DOC_DIR, f))]
supported = [f for f in files if os.path.splitext(f)[1].lower() in (".txt", ".md", ".pdf")]

if not supported:
    print(f"\n  [WARN] No supported files found.")
    print(f"  Put .txt / .md / .pdf files into: {DOC_DIR}")
    sys.exit(1)

total_chunks = 0
for filename in supported:
    filepath = os.path.join(DOC_DIR, filename)
    text = read_file(filepath)
    if not text or not text.strip():
        print(f"  [SKIP] {filename} (empty)")
        continue

    chunks = chunk_text(text)
    if not chunks:
        continue

    ids   = [f"{filename}_chunk{i}" for i in range(len(chunks))]
    metas = [{"source": filename, "chunk": i} for i in range(len(chunks))]
    embeddings = model.encode(chunks).tolist()

    collection.add(
        ids=ids,
        documents=chunks,
        metadatas=metas,
        embeddings=embeddings,
    )
    print(f"  [OK] {filename} -> {len(chunks)} chunks")
    total_chunks += len(chunks)

print(f"\n[DONE] Imported {len(supported)} files, {total_chunks} chunks")
print(f"  DB location: {os.path.abspath(DB_DIR)}")
