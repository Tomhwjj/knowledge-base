"""
知识库文档导入脚本 (v3)
- BGE 中文 Embedding 模型（精度 +20%）
- 递归语义分块（保留段落/句子完整性）
- pdfplumber 表格感知解析（保留财报表格结构）
- 支持 .txt / .md / .pdf
"""
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from config import (
    DOC_DIR, DB_DIR,
    EMBEDDING_MODEL,
    CHUNK_SIZE, CHUNK_OVERLAP, SEPARATORS,
    USE_PDFPLUMBER,
)
import chromadb
from sentence_transformers import SentenceTransformer


# ═══════════════════════════════════════════════
# 递归语义分块器
# ═══════════════════════════════════════════════

def recursive_chunk(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    separators: list[str] | None = None,
) -> list[str]:
    """
    按分隔符优先级递归切分，尽可能在语义边界断开。

    优先级: 段落 → 换行 → 句号 → 分号 → 逗号 → 空格 → 硬切
    """
    if separators is None:
        separators = SEPARATORS

    if not text or not text.strip():
        return []

    if len(text) <= chunk_size:
        return [text]

    sep = ""
    for candidate in separators:
        if candidate in text:
            sep = candidate
            break

    if not sep:
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append(text[start:end])
            start += chunk_size - chunk_overlap
        return chunks

    splits = text.split(sep)
    splits = [s + sep for s in splits[:-1]] + [splits[-1:][0]]

    chunks = []
    current = ""

    for split in splits:
        if not split.strip():
            if current:
                current += split
            continue

        if len(current) + len(split) <= chunk_size:
            current += split
        else:
            if current.strip():
                if len(current) >= chunk_size // 2:
                    chunks.append(current)
                    current = split
                else:
                    current += split
            else:
                current = split

        while len(current) > chunk_size:
            next_seps = separators[separators.index(sep) + 1:] if sep in separators else [""]
            sub_chunks = recursive_chunk(current, chunk_size, chunk_overlap, next_seps)
            if len(sub_chunks) > 1:
                chunks.extend(sub_chunks[:-1])
                current = sub_chunks[-1]
            else:
                chunks.append(current[:chunk_size])
                current = current[chunk_size - chunk_overlap:]
                break

    if current.strip():
        chunks.append(current)

    return chunks


# ═══════════════════════════════════════════════
# 文档读取
# ═══════════════════════════════════════════════

def _read_pdf_plumber(filepath: str) -> str | None:
    """用 pdfplumber 提取文本，自动识别表格并转为 Markdown table"""
    import pdfplumber

    parts = []
    with pdfplumber.open(filepath) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            # 先提取文本
            text = page.extract_text()
            if text:
                parts.append(text)

            # 再提取表格，转为 Markdown table 格式
            tables = page.extract_tables()
            for table in tables:
                if not table:
                    continue
                md_lines = []
                for row_idx, row in enumerate(table):
                    cells = [str(c).replace("\n", " ") if c else "" for c in row]
                    md_lines.append("| " + " | ".join(cells) + " |")
                    if row_idx == 0:  # 表头后加分界线
                        md_lines.append("| " + " | ".join(["---"] * len(cells)) + " |")
                parts.append("\n".join(md_lines))

    return "\n\n".join(parts)


def _read_pdf_fitz(filepath: str) -> str:
    """用 PyMuPDF 提取纯文本（回退方案）"""
    import fitz
    doc = fitz.open(filepath)
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    return text


def read_file(filepath: str) -> str | None:
    """读取文档内容，PDF 优先用 pdfplumber（保留表格）"""
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == ".pdf":
            if USE_PDFPLUMBER:
                try:
                    return _read_pdf_plumber(filepath)
                except ImportError:
                    print("  [提示] pdfplumber 未安装，回退到 PyMuPDF（表格会丢失结构）")
                    print("         安装: pip install pdfplumber")
                    return _read_pdf_fitz(filepath)
            else:
                return _read_pdf_fitz(filepath)

        elif ext in (".txt", ".md"):
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        else:
            return None
    except Exception as e:
        print(f"  [WARN] 读取失败 {filepath}: {e}")
        return None


# ═══════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════

def main():
    print(f"[1/3] 加载 Embedding 模型: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)

    print(f"[2/3] 打开向量库: {DB_DIR}")
    chroma = chromadb.PersistentClient(path=DB_DIR)

    import datetime
    collection_name = f"knowledge_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    collection = chroma.create_collection(name=collection_name)

    # 加载 .kbignore
    kbignore_path = os.path.join(DOC_DIR, ".kbignore")
    ignore_rules = []
    if os.path.exists(kbignore_path):
        with open(kbignore_path, "r", encoding="utf-8") as f:
            ignore_rules = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
    import fnmatch

    def should_ignore(fname):
        for rule in ignore_rules:
            if fnmatch.fnmatch(fname, rule):
                return True
            if rule.endswith("/") and fname.startswith(rule):
                return True
        return False

    print(f"[3/3] 扫描文档: {DOC_DIR}")

    def walk_files(root: str):
        """递归扫描，返回相对路径列表"""
        result = []
        for entry in os.listdir(root):
            full = os.path.join(root, entry)
            rel = os.path.relpath(full, DOC_DIR)
            if entry.startswith(".") or should_ignore(rel):
                continue
            if os.path.isfile(full):
                if os.path.splitext(entry)[1].lower() in (".txt", ".md", ".pdf"):
                    result.append(rel)
            elif os.path.isdir(full):
                result.extend(walk_files(full))
        return result

    supported = walk_files(DOC_DIR)

    if not supported:
        print(f"\n  [WARN] 没有找到支持的文档。")
        print(f"  把 .txt / .md / .pdf 放到: {DOC_DIR}")
        sys.exit(1)

    total_chunks = 0
    for filename in supported:
        filepath = os.path.join(DOC_DIR, filename)
        text = read_file(filepath)
        if not text or not text.strip():
            print(f"  [SKIP] {filename} (空文件)")
            continue

        chunks = recursive_chunk(text)
        if not chunks:
            continue

        safe_name = filename.replace("\\", "/").replace("/", "_")
        ids   = [f"{safe_name}_chunk{i}" for i in range(len(chunks))]
        metas = [{"source": filename, "chunk": i, "char_count": len(c)}
                 for i, c in enumerate(chunks)]
        embeddings = model.encode(chunks, show_progress_bar=True).tolist()

        collection.add(
            ids=ids,
            documents=chunks,
            metadatas=metas,
            embeddings=embeddings,
        )
        avg_len = sum(len(c) for c in chunks) // len(chunks)
        print(f"  [OK] {filename} → {len(chunks)} 块 (平均 {avg_len} 字/块)")
        total_chunks += len(chunks)

    # 删除旧集合
    all_collections = chroma.list_collections()
    for col in all_collections:
        if col.name.startswith("knowledge_") and col.name != collection_name:
            chroma.delete_collection(name=col.name)
            print(f"  [清理] 已删除旧集合: {col.name}")

    print(f"\n[DONE] 导入 {len(supported)} 个文件, {total_chunks} 块")
    print(f"  集合名: {collection_name}")
    print(f"  位置: {os.path.abspath(DB_DIR)}")


if __name__ == "__main__":
    main()
