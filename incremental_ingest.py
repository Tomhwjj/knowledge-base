"""
增量入库脚本 — 只处理新增/修改的文件，不重建全库。
每次记笔记后自动跑这个，比全量 ingest.py 快几十倍。

用法:
  python incremental_ingest.py
  python incremental_ingest.py --dry-run    # 只看哪些文件会变，不动手
"""
import os
import sys
import json
import hashlib
import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from config import (
    DOC_DIR, DB_DIR, EMBEDDING_MODEL,
    CHUNK_SIZE, CHUNK_OVERLAP, SEPARATORS,
)
import chromadb
from sentence_transformers import SentenceTransformer

MANIFEST_PATH = os.path.join(DOC_DIR, ".ingest_manifest.json")


# ═══════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════

def file_hash(filepath: str) -> str:
    """文件 MD5，用于检测内容变化"""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest() -> dict:
    """加载入库清单"""
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_manifest(manifest: dict):
    """保存入库清单"""
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def recursive_chunk(text, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP,
                    separators=None):
    """递归语义分块 — 同 ingest.py"""
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
            chunks.append(text[start:start + chunk_size])
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
            sub = recursive_chunk(current, chunk_size, chunk_overlap, next_seps)
            if len(sub) > 1:
                chunks.extend(sub[:-1])
                current = sub[-1]
            else:
                chunks.append(current[:chunk_size])
                current = current[chunk_size - chunk_overlap:]
                break
    if current.strip():
        chunks.append(current)
    return chunks


def read_file(filepath: str) -> str | None:
    """同 ingest.py"""
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == ".pdf":
            from config import USE_PDFPLUMBER
            if USE_PDFPLUMBER:
                try:
                    import pdfplumber
                    parts = []
                    with pdfplumber.open(filepath) as pdf:
                        for page in pdf.pages:
                            text = page.extract_text()
                            if text:
                                parts.append(text)
                            tables = page.extract_tables()
                            for table in tables:
                                if not table:
                                    continue
                                md_lines = []
                                for ri, row in enumerate(table):
                                    cells = [str(c).replace("\n", " ") if c else "" for c in row]
                                    md_lines.append("| " + " | ".join(cells) + " |")
                                    if ri == 0:
                                        md_lines.append("| " + " | ".join(["---"] * len(cells)) + " |")
                                parts.append("\n".join(md_lines))
                    return "\n\n".join(parts)
                except ImportError:
                    pass
            import fitz
            doc = fitz.open(filepath)
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
            return text
        elif ext in (".txt", ".md"):
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
    except Exception as e:
        print(f"  [WARN] 读取失败 {filepath}: {e}")
    return None


def load_kbignore() -> list[str]:
    """读取 .kbignore，返回忽略规则列表"""
    ignore_path = os.path.join(DOC_DIR, ".kbignore")
    if not os.path.exists(ignore_path):
        return []
    with open(ignore_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f
                if line.strip() and not line.strip().startswith("#")]


def should_ignore(filename: str, rules: list[str]) -> bool:
    """检查文件是否匹配忽略规则（简单通配符）"""
    import fnmatch
    for rule in rules:
        if fnmatch.fnmatch(filename, rule):
            return True
        if rule.endswith("/") and filename.startswith(rule):
            return True
    return False


def find_latest_collection(chroma_client):
    """找最新的 knowledge_ 集合"""
    cols = [c.name for c in chroma_client.list_collections()
            if c.name.startswith("knowledge_")]
    if not cols:
        raise RuntimeError("向量库为空，请先运行 ingest.py 做一次全量导入")
    return sorted(cols)[-1]


# ═══════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════

def main(dry_run: bool = False):
    print(f"增量入库{' (预览模式)' if dry_run else ''}", flush=True)
    print(f"  文档目录: {DOC_DIR}", flush=True)

    # ── 递归扫描文件 ──
    ignore_rules = load_kbignore()

    def walk_files(root: str):
        """递归扫描，返回相对路径列表"""
        result = []
        for entry in os.listdir(root):
            full = os.path.join(root, entry)
            rel = os.path.relpath(full, DOC_DIR)
            if entry.startswith(".") or should_ignore(rel, ignore_rules):
                continue
            if os.path.isfile(full):
                if os.path.splitext(entry)[1].lower() in (".txt", ".md", ".pdf"):
                    result.append(rel)
            elif os.path.isdir(full):
                result.extend(walk_files(full))
        return result

    all_files = walk_files(DOC_DIR)

    if not all_files:
        print("  没有文件", flush=True)
        return

    # ── 对比 manifest ──
    manifest = load_manifest()
    new_files = []
    changed_files = []
    deleted_files = [f for f in manifest if f not in all_files]
    unchanged = []

    for f in all_files:
        filepath = os.path.join(DOC_DIR, f)
        h = file_hash(filepath)
        if f not in manifest:
            new_files.append((f, h))
        elif manifest[f].get("hash") != h:
            changed_files.append((f, h))
        else:
            unchanged.append(f)

    print(f"  新增: {len(new_files)}  修改: {len(changed_files)}  "
          f"删除: {len(deleted_files)}  不变: {len(unchanged)}", flush=True)

    if new_files:
        for f, _ in new_files:
            print(f"    + {f}", flush=True)
    if changed_files:
        for f, _ in changed_files:
            print(f"    ~ {f}", flush=True)
    if deleted_files:
        for f in deleted_files:
            print(f"    - {f}", flush=True)

    if not new_files and not changed_files and not deleted_files:
        print("  没有变化，无需更新", flush=True)
        return

    if dry_run:
        return

    # ── 加载模型 ──
    print(f"\n  加载 Embedding: {EMBEDDING_MODEL} ...", end=" ", flush=True)
    model = SentenceTransformer(EMBEDDING_MODEL)
    print("OK", flush=True)

    # ── 连接向量库 ──
    chroma = chromadb.PersistentClient(path=DB_DIR)
    collection_name = find_latest_collection(chroma)
    collection = chroma.get_collection(name=collection_name)
    print(f"  向量库: {collection_name} ({collection.count()} 块)", flush=True)

    # ── 删除已移除文件的旧块 ──
    for f in deleted_files:
        try:
            old_ids = [f"{f}_chunk{i}" for i in range(manifest[f].get("chunks", 0))]
            if old_ids:
                collection.delete(ids=old_ids)
                print(f"  [-] {f} ({len(old_ids)} 块)", flush=True)
        except Exception as e:
            print(f"  [WARN] 删除 {f} 失败: {e}", flush=True)

    # ── 处理新增和修改的文件 ──
    to_process = new_files + changed_files
    total_added = 0

    for filename, fhash in to_process:
        safe_name = filename.replace("\\", "/").replace("/", "_")

        # 先删除旧块（如果是修改）
        if filename in manifest:
            old_ids = [f"{safe_name}_chunk{i}" for i in range(manifest[filename].get("chunks", 0))]
            if old_ids:
                try:
                    collection.delete(ids=old_ids)
                except Exception:
                    pass

        filepath = os.path.join(DOC_DIR, filename)
        text = read_file(filepath)
        if not text or not text.strip():
            print(f"  [SKIP] {filename} (空)", flush=True)
            continue

        chunks = recursive_chunk(text)
        if not chunks:
            continue

        ids = [f"{safe_name}_chunk{i}" for i in range(len(chunks))]
        metas = [{"source": filename, "chunk": i, "char_count": len(c)}
                 for i, c in enumerate(chunks)]
        embeddings = model.encode(chunks, show_progress_bar=False).tolist()

        collection.add(ids=ids, documents=chunks, metadatas=metas, embeddings=embeddings)

        manifest[filename] = {
            "hash": fhash,
            "chunks": len(chunks),
            "last_ingested": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        total_added += len(chunks)

        action = "+" if filename in dict(new_files) else "~"
        print(f"  [{action}] {filename} → {len(chunks)} 块", flush=True)

    # ── 清理已删除的 manifest 条目 ──
    for f in deleted_files:
        del manifest[f]

    save_manifest(manifest)
    print(f"\n[DONE] 新增 {total_added} 块 → 总计 {collection.count()} 块", flush=True)


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    main(dry_run=dry)
