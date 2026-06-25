"""
知识库文档导入脚本 (v2)
- BGE 中文 Embedding 模型（精度 +20%）
- 递归语义分块（保留段落/句子完整性）
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

    这样切出来的块比固定 500 字符更完整：
    - 不会把一句话劈成两半
    - 表格/列表尽量保持在同一块
    - 段落是天然的语义单元
    """
    if separators is None:
        separators = SEPARATORS

    # 空文本直接返回
    if not text or not text.strip():
        return []

    # 文本本身就够短，直接返回
    if len(text) <= chunk_size:
        return [text]

    # 找第一个在文本中出现的分隔符
    sep = ""
    for candidate in separators:
        if candidate in text:
            sep = candidate
            break

    # 没有找到任何分隔符 → 硬切
    if not sep:
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append(text[start:end])
            start += chunk_size - chunk_overlap
        return chunks

    # 用分隔符切开
    splits = text.split(sep)
    # 把分隔符还给每个片段（除了最后一个）
    splits = [s + sep for s in splits[:-1]] + [splits[-1:][0]]

    # 合并太短的片段，递归切分太长的片段
    chunks = []
    current = ""

    for split in splits:
        # 跳过纯空片段
        if not split.strip():
            if current:
                current += split  # 保留格式空白
            continue

        if len(current) + len(split) <= chunk_size:
            # 当前块还能塞
            current += split
        else:
            # 当前块满了
            if current.strip():
                # 如果当前块还比较短，不要急着输出，再攒一下
                if len(current) >= chunk_size // 2:
                    chunks.append(current)
                    current = split
                else:
                    # 太短就和下一个合并试试
                    current += split
            else:
                current = split

        # 如果当前块超长了，用下一个分隔符递归切
        while len(current) > chunk_size:
            # 用更细粒度的分隔符递归
            next_seps = separators[separators.index(sep) + 1:] if sep in separators else [""]
            sub_chunks = recursive_chunk(current, chunk_size, chunk_overlap, next_seps)
            if len(sub_chunks) > 1:
                chunks.extend(sub_chunks[:-1])
                current = sub_chunks[-1]
            else:
                # 递归也切不动就硬切
                chunks.append(current[:chunk_size])
                current = current[chunk_size - chunk_overlap:]
                break

    if current.strip():
        chunks.append(current)

    return chunks


# ═══════════════════════════════════════════════
# 文档读取
# ═══════════════════════════════════════════════

def read_file(filepath: str) -> str | None:
    """读取文档内容，支持 .txt / .md / .pdf"""
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

    # 每次导入建新集合，避免新旧模型向量混在一起
    import datetime
    collection_name = f"knowledge_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    collection = chroma.create_collection(name=collection_name)

    print(f"[3/3] 扫描文档: {DOC_DIR}")
    files = [f for f in os.listdir(DOC_DIR)
             if os.path.isfile(os.path.join(DOC_DIR, f))]
    supported = [f for f in files
                 if os.path.splitext(f)[1].lower() in (".txt", ".md", ".pdf")]

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

        ids   = [f"{filename}_chunk{i}" for i in range(len(chunks))]
        metas = [{"source": filename, "chunk": i, "char_count": len(c)} for i, c in enumerate(chunks)]
        embeddings = model.encode(chunks, show_progress_bar=True).tolist()

        collection.add(
            ids=ids,
            documents=chunks,
            metadatas=metas,
            embeddings=embeddings,
        )
        print(f"  [OK] {filename} → {len(chunks)} 块 (平均 {sum(len(c) for c in chunks)//len(chunks)} 字/块)")
        total_chunks += len(chunks)

    # 删除旧集合，只保留最新的
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
