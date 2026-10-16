"""重建向量库：读语料文件 → 切分 → 嵌入 → Chroma（支持多文件来源）

本版改动（扩语料 + 去重卡片）：
  1. **支持多文件来源**。默认只读 config.DOC_PATH（data/my_doc.txt），
     也可以一次给多个：python -m scripts.build_index a.txt b.txt
  2. **chunk_size 500 → 1000**（overlap 150）。语料从 1 页扩到几百页后，
     500 字会把长文切得太碎；1000 字更接近"一段完整信息"。
  3. **把来源 URL 写进 metadata**。解析语料里的 `=== url ===` 标记，
     每个 chunk 的 metadata 变成 {"source": <该页 URL>, "file": <文件名>}；
     没有标记的文件退化为记文件路径。这样检索命中后能溯源。
  4. **安全闸**：先读文件 + 切分，若得到 0 个 chunk 就**直接放弃、不删旧库**
     （避免路径写错 / 文件为空时，把还能用的向量库清掉）。

用法：
  python -m scripts.build_index                                  # 默认读 data/my_doc.txt
  python -m scripts.build_index data/my_doc.txt                  # 显式指定
  python -m scripts.build_index --chunk-size 800 --chunk-overlap 120
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

# 允许从项目根或任意工作目录执行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_community.embeddings import DashScopeEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend import config

# 语料分节标记：=== https://... ===
SECTION_RE = re.compile(r"^=== (.*?) ===$", re.M)


def parse_sections(text: str) -> list[tuple[str, str]]:
    """把 `=== url ===` 分节文本拆成 [(url, body)]；没有标记则返回 []。"""
    parts = re.split(r"^=== (.*?) ===$", text, flags=re.M)
    out = []
    for i in range(1, len(parts) - 1, 2):
        out.append((parts[i].strip(), parts[i + 1]))
    return out


def load_documents(paths: list[Path], splitter: RecursiveCharacterTextSplitter) -> list[Document]:
    """把若干语料文件切成 Document 列表，并把来源写进 metadata。"""
    docs: list[Document] = []

    for path in paths:
        if not path.exists():
            print(f"[warn] 跳过不存在的文件：{path}")
            continue

        text = path.read_text(encoding="utf-8")
        sections = parse_sections(text)

        if sections:
            # 有分节标记：逐页切分，metadata.source = 该页 URL
            for url, body in sections:
                body = body.strip()
                if not body:
                    continue
                for piece in splitter.split_text(body):
                    if piece.strip():
                        docs.append(Document(
                            page_content=piece,
                            metadata={"source": url, "file": path.name},
                        ))
            print(f"[load] {path.name}: {len(sections)} 页（带 URL 标记）")
        else:
            # 没有标记：整文件当一份文档，metadata.source = 文件路径
            for piece in splitter.split_text(text):
                if piece.strip():
                    docs.append(Document(
                        page_content=piece,
                        metadata={"source": str(path), "file": path.name},
                    ))
            print(f"[load] {path.name}: 无分节标记，按整文件处理")

    return docs


def main() -> int:
    parser = argparse.ArgumentParser(description="重建向量库（支持多文件来源）")
    parser.add_argument("sources", nargs="*", help="语料文件路径；不填则用 config.DOC_PATH")
    parser.add_argument("--chunk-size", type=int, default=1000, help="切分长度（默认 1000）")
    parser.add_argument("--chunk-overlap", type=int, default=150, help="切分重叠（默认 150）")
    args = parser.parse_args()

    # 1) 确定来源文件
    paths = [Path(p) for p in args.sources] if args.sources else [config.DOC_PATH]

    # 2) 先切分（此步不碰向量库）
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap
    )
    docs = load_documents(paths, splitter)
    print(f"[split] 共 {len(docs)} 个 chunk（chunk_size={args.chunk_size}, "
          f"overlap={args.chunk_overlap}）")

    # 3) 安全闸：一个 chunk 都没有就放弃，**不删旧库**
    if not docs:
        print("[FAIL] 没有切出任何 chunk，已放弃；旧向量库保持不动。请检查语料文件。")
        return 1

    # 4) 删旧库（到这里才动它）
    if config.VECTOR_DIR.exists():
        print(f"[reset] 删除旧向量库：{config.VECTOR_DIR}")
        shutil.rmtree(config.VECTOR_DIR)

    # 5) 嵌入 + 存库
    print("[embed] 正在嵌入（会调 DashScope API，页数多时较慢）...")
    embeddings = DashScopeEmbeddings(model=config.EMBEDDING_MODEL)
    vectorstore = Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        persist_directory=str(config.VECTOR_DIR),
        collection_name=config.COLLECTION_NAME,
    )

    count = vectorstore._collection.count()
    print("=" * 60)
    print(f"[OK] 向量库条数：{count}")

    # 抽样看一条 metadata，确认来源 URL 写进去了
    sample = vectorstore._collection.get(limit=1, include=["metadatas"])
    if sample.get("metadatas"):
        print(f"[sample] metadata = {sample['metadatas'][0]}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
